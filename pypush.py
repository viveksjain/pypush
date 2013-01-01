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
		# Check if current directory is a git repo
		if subprocess.call(['git', 'rev-parse']): # If this or any parent directory isn't a git repo, this command returns non-zero and prints an error message
			print "Hint: run 'git init'"
			sys.exit(1)

		self.user = flags.user
		self.path = flags.dest
		self.quiet = flags.quiet
		self.verbose = flags.verbose
		self.show_ignored = flags.show_ignored
		self.cwd = os.getcwd()
		if self.path[-1] != '/': # Ensure path ends in a slash, i.e. it is a directory
			self.path += '/'

		args = ['ssh', '-t', '-t', # Force tty allocation - this prevents certain error messages
			'-M', '-S', '~/.ssh/socket-%r@%h:%p', # Create a master TCP connection that we can use later every time a file changes
			'-fN', # Go to the background when the connection is established - so after this command returns, we can be sure that the master connection has been created
			self.user]
		if subprocess.call(args):
			print 'Error with ssh, aborting'
			sys.exit(1)

		atexit.register(subprocess.call,
			['ssh', '-O', 'exit', '-S', '~/.ssh/socket-%r@%h:%p', self.user], stderr=subprocess.PIPE) # Close the master connection before exiting

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
		print 'Generating list of files'
		args = ['git', 'ls-files', '-c', '-o', '--exclude-standard'] # Show all non-excluded files in the current directory
		output = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]
		tf = tempfile.NamedTemporaryFile(delete=False)
		for line in string.split(output, '\n'):
			if line != '':
				tf.write('/' + line + '\n')
		tf.close()

		print 'Performing initial one-way sync'
		args = ['rsync', '-az', # Usual flags - archive, compress
			'-e', 'ssh -S ~/.ssh/socket-%r@%h:%p', # Connect to the master connection from earlier
			'--include-from=' + tf.name, # Include the list of files we got from git
			'--exclude=*', # Exclude everything else
			'--delete-excluded', # Delete excluded files
			'./', # Sync current directory
			self.user + ':' + self.escape(self.path)]
		if self.verbose:
			args.append('-v')
		if subprocess.call(args):
			print 'Error with rsync, aborting'
			sys.exit(1)
		os.remove(tf.name)
		print 'Startup complete, waiting for file changes\n'

	def print_quiet(self, message):
		"""Only print the given message if not in quiet mode.

		If message ends in a '\r', then it is printed without a newline. On most
		shells, this means that a subsequent call to print will overwrite that
		line.
		"""
		if not self.quiet:
			if message[-1] == '\r':
				print message,
				sys.stdout.flush()
			else:
				print message

	def should_ignore(self, filename):
		"""Return whether changes to filename should be ignored."""
		args = ['git', 'ls-files', filename, '-c', '-o', '--exclude-standard']
		if subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]: # If git outputs something, then that file isn't ignored
			return False
		return True

	def relative_path(self, filename):
		"""Convert filename to a path relative to the current directory."""
		return filename.replace(self.cwd, '', 1)[1:]

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
			self.print_quiet(output + '\r')
		args = ['rsync', '-az', '-e', 'ssh -S ~/.ssh/socket-%r@%h:%p', path, self.user + ':' + self.escape(self.path + path)]
		if self.verbose:
			args.append('-v')
		subprocess.call(args)
		if output:
			self.print_quiet(output + '...pushed')

	def on_moved(self, src, dest, output):
		self.print_quiet(output + '\r')
		if not self.should_ignore(dest):
			self.on_modified(dest)
		self.on_deleted(src)
		self.print_quiet(output + '...pushed')

	def on_deleted(self, path, output=''):
		if output:
			self.print_quiet(output + '\r')
		args = ['ssh', '-S', '~/.ssh/socket-%r@%h:%p', self.user, 'rm -f ' + self.escape(self.path + path)]
		subprocess.call(args)
		if output:
			self.print_quiet(output + '...pushed')

def main():
	parser = argparse.ArgumentParser(description="""Continuously push changes in the current directory to a remote server.
			Files that are ignored by git will not be pushed (therefore the current directory must be a git repo).""",
		epilog="""WARNING: pypush only performs a one-way sync. If you make
			changes directly on the remote machine, they may be overwritten at
			any time by changes made locally.""")
	parser.add_argument('-q', '--quiet', action='store_const', default=False, const=True,
		help='quiet mode - do not show output whenever a file changes')
	parser.add_argument('-v', '--verbose', action='store_const', default=False, const=True,
		help='verbose mode - run rsync in verbose mode')
	parser.add_argument('-s', '--skip-init', action='store_const', default=False, const=True,
		help='skip the initial one-way sync performed on startup')
	parser.add_argument('-i', '--show-ignored', action='store_const', default=False, const=True,
		help='print output even when ignored files are created or modified (this flag is overridden by quiet mode)')
	parser.add_argument('--version', action='version', version='%(prog)s 1.1')
	parser.add_argument('user', metavar='[user@]hostname', help='the remote machine (and optional user name) to login to')
	parser.add_argument('dest', help='the path to the remote directory to push changes to')
	args = parser.parse_args()

	event_handler = PypushHandler(args)
	observer = watchdog.observers.Observer()
	observer.schedule(event_handler, path='.', recursive=True)
	observer.start()
	try:
		while True:
			time.sleep(10)
	except KeyboardInterrupt:
		observer.stop()
	observer.join()

if __name__ == '__main__':
	main()