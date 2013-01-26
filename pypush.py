#!/usr/bin/env python

import os
import time
import watchdog.events
import watchdog.observers
import watchdog.utils
import signal
import sys
import subprocess
import string
import tempfile
import argparse
import re
import atexit

class PypushHandler(watchdog.events.FileSystemEventHandler):
	"""Push all changes in the current directory to a remote server."""
	def __init__(self, flags):
		if flags.include_all:
			self.vcs = None
			# vcs stores the version control system used to check whether a file
			# should be ignored or not - 'git', 'hg' or None
		else:
			# If this or any parent directory isn't a git/hg repo, the commands
			# below return non-zero status
			if subprocess.Popen(['git', 'rev-parse'], stderr=subprocess.PIPE).communicate()[1]:
				if subprocess.Popen(['hg', 'root'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[1]:
					print "This isn't a git/hg repo, no files will be ignored"
					self.vcs = None
				else:
					self.vcs = 'hg'
			else:
				self.vcs = 'git'

		if flags.skip_init and flags.exit_after:
			print 'Error: cannot use flags -s and -e together.'
			sys.exit(1)

		self.user = flags.user
		self.path = flags.dest
		self.quiet = flags.quiet
		self.verbose = flags.verbose
		self.show_ignored = flags.show_ignored
		self.exit_after = flags.exit_after
		self.port = str(flags.port) # Store as string to allow passing it as a flag to ssh/rsync
		self.keep_extra = flags.keep_extra;
		self.cwd = os.getcwd() + '/'
		if self.path[-1] != '/': # Ensure path ends in a slash, i.e. it is a directory
			self.path += '/'

		args = ['ssh', '-t', '-t', # Force tty allocation - this prevents certain error messages
			'-M', '-S', '~/.ssh/socket-%r@%h:%p', # Create a master TCP connection that we can use later every time a file changes
			'-fN', # Go to the background when the connection is established - so after this command returns, we can be sure that the master connection has been created
			'-p', self.port,
            self.user]
		if subprocess.call(args):
			print 'Error with ssh, aborting'
			sys.exit(1)

		atexit.register(subprocess.call, ['ssh', '-O', 'exit', '-S',
			'~/.ssh/socket-%r@%h:%p', '-p', self.port, self.user], stderr=subprocess.PIPE) # Close the master connection before exiting

		if flags.skip_init:
			print 'Waiting for file changes\n'
		else:
			self.sync()

	def escape(self, path):
		"""Escape all special characters in path, except the tilde (~)."""
		return re.sub(r'([\|&;<>\(\)\$`\\"\' \*\?\[#])', # List of special characters from http://pubs.opengroup.org/onlinepubs/009695399/utilities/xcu_chap02.html
			r'\\\1', path)

	def sync(self):
		"""Perform a one-way sync to the remote directory.

		Exclude any files ignored by git.
		"""
		if self.vcs == 'git':
			args = ['git', 'ls-files', '-i', '-o', '--exclude-standard'] # Show all untracked, ignored files in the current directory
		elif self.vcs == 'hg':
			args = ['hg', 'status', '-i', '-n']

		print 'Performing initial one-way sync'
		if self.vcs:
			output = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]
			tf = tempfile.NamedTemporaryFile(delete=False)
			# Exclude the git directory
			tf.write('/.git/\n')
			tf.write('/.hg/\n')
			for line in string.split(output, '\n'):
				if line != '':
					tf.write('/' + line + '\n')
			tf.close()

		args = ['rsync', '-az', # Usual flags - archive, compress
			'-e', 'ssh -S ~/.ssh/socket-%r@%h:%p -p ' + self.port, # Connect to the master connection from earlier
			'./', # Sync current directory
			self.user + ':' + self.escape(self.path)]

		if self.vcs:
			args.append('--exclude-from=' + tf.name);
			if not self.keep_extra:
				args.append('--delete-excluded');
		elif not self.keep_extra:
			args.append('--delete')
		if self.verbose:
			args.append('-v')

		if subprocess.call(args):
			print 'Error with rsync, aborting'
			sys.exit(1)

		if self.vcs:
			os.remove(tf.name)
		if self.exit_after:
			print 'Done'
			sys.exit(0)
		else:
			print 'Startup complete, waiting for file changes\n'

	def print_quiet(self, message, newline=True):
		"""Only print the given message if not in quiet mode.

		Optionally print without a newline.
		"""
		if not self.quiet:
			if newline:
				print message
			else:
				sys.stdout.write(message)
				sys.stdout.flush()

	def should_ignore(self, filename):
		"""Return whether changes to filename should be ignored."""
		if not self.vcs:
			return False
		elif filename.startswith(self.cwd + '.git/') or \
			filename.startswith(self.cwd + '.hg/'): # Make sure we exclude files inside the git/hg directory
			return True
		if self.vcs == 'git':
			args = ['git', 'ls-files', '-i', '-o', '--exclude-standard', filename]
		else:
			assert self.vcs == 'hg'
			args = ['hg', 'status', '-i', '-n', filename]
		if subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]: # If git outputs something, then that file is ignored
			return True
		return False

	def relative_path(self, filename):
		"""Convert filename to a path relative to the current directory."""
		return filename.replace(self.cwd, '', 1)

	def dispatch(self, event):
		"""Dispatch events to the appropriate methods."""
		if not event.is_directory: # Git doesn't care about directories, so neither do we
			path = self.relative_path(event.src_path)
			if watchdog.utils.has_attribute(event, 'dest_path'): # File move
				dest = self.relative_path(event.dest_path)
				self.on_moved(path, dest, path + ' moved to ' + dest)
			elif event.event_type == 'deleted':
				# We can't do 'git ls-files' on a deleted file, so just try to
				# delete it - if it doesn't exist on the remote, nothing will happen
				self.on_deleted(path, path + ' deleted')
			else: # Created or modified
				if not self.should_ignore(event.src_path):
					self.on_modified(path, path + ' ' + event.event_type)
				elif self.show_ignored:
					self.print_quiet(path + ' ' + event.event_type + ' (ignored)')

	def on_modified(self, path, output=''):
		"""Call rsync on the given relative path."""
		if output:
			self.print_quiet(output, False)
		args = ['rsync', '-az', '-e', 'ssh -S ~/.ssh/socket-%r@%h:%p -p ' + self.port, path, self.user + ':' + self.escape(self.path + path)]
		if self.verbose:
			args.append('-v')
		subprocess.call(args)
		if output:
			self.print_quiet('...pushed')

	def on_moved(self, src, dest, output):
		if self.should_ignore(dest):
			self.on_deleted(src, src + ' deleted')
		else:
			self.print_quiet(output, False)
			# Try to move src to dest on the remote with ssh and mv. Then call
			# rsync on it, in case either src was changed on the remote, or it
			# didn't exist.
			args = ['ssh', '-S', '~/.ssh/socket-%r@%h:%p', '-p', self.port, self.user, 'mv ' + self.escape(self.path + src) + ' ' + self.escape(self.path + dest)]
			subprocess.call(args, stderr=subprocess.PIPE)
			self.on_modified(dest)
		self.print_quiet('...pushed')

	def on_deleted(self, path, output=''):
		if output:
			self.print_quiet(output, False)
		args = ['ssh', '-S', '~/.ssh/socket-%r@%h:%p', '-p', self.port, self.user, 'rm -f ' + self.escape(self.path + path)]
		subprocess.call(args)
		if output:
			self.print_quiet('...pushed')

def main():
	parser = argparse.ArgumentParser(description="""Continuously push changes in the current directory to a remote server.
			If this is a Git/Mercurial directory, files that are ignored by Git/Mercurial will not be pushed.""",
		epilog="""WARNING: pypush only performs a one-way sync. If you make
			changes directly on the remote machine, they may be overwritten at
			any time by changes made locally.""")
	parser.add_argument('-q', '--quiet', action='store_true',
		help='quiet mode - do not show output whenever a file changes')
	parser.add_argument('-v', '--verbose', action='store_true',
		help='verbose mode - run rsync in verbose mode')
	parser.add_argument('-s', '--skip-init', action='store_true',
		help='skip the initial one-way sync performed on startup')
	parser.add_argument('-i', '--show-ignored', action='store_true',
		help='print output even when ignored files are created or modified (this flag is overridden by quiet mode)')
	parser.add_argument('-e', '--exit-after', action='store_true',
		help='exit after the initial sync, i.e. do not monitor the directory for changes')
	parser.add_argument('-a', '--include-all', action='store_true',
		help='do not ignore any files')
	parser.add_argument('-p', '--port', type=int, default=22, help='the SSH port to use')
	parser.add_argument('-k', '--keep-extra', action='store_true',
		help='keep files on the remote that do not exist locally')

	parser.add_argument('--version', action='version', version='%(prog)s 1.2')
	parser.add_argument('user', metavar='user@hostname', help='the remote machine (and optional user name) to login to')
	# The user argument is passed on to rsync and ssh, so actually the 'user@'
	# part is optional, but using metavar='[user@]hostname' causes an error
	# because of a bug in argparse - see http://bugs.python.org/issue11874
	parser.add_argument('dest', help='the path to the remote directory to push changes to')
	args = parser.parse_args()

	observer = watchdog.observers.Observer()
	observer.schedule(PypushHandler(args), path='.', recursive=True)
	observer.start()
	try:
		while True:
			time.sleep(10)
	except KeyboardInterrupt:
		observer.stop()
	observer.join()

if __name__ == '__main__':
	main()