Pypush
======

Problem
-------
I often work on files that are stored remotely. I can either work on them
locally and not have to deal with network latency, or I can work remotely and
not need to reupload files every time I change them. Both options are
frustrating and leave a lot to be desired.

Solution
--------
Pypush continuously monitors your local directory and immediately uploads any
changes you make to your specified remote directory. You can also just make some
changes locally, then periodically run pypush to synchronize all those changes
to the remote directory.

What sets pypush apart is its real-time sync, and its integration with
Git/Mercurial. Any local files ignored (and untracked) by Git/Mercurial will not
be pushed to the remote machine.

Requirements
------------
Requires a Unix system - Mac or Linux. May work on Windows with the right tools
installed. If you are interested in getting it to work on Windows, [open a new
issue](https://github.com/viveksjain/pypush/issues/new). The remote machine must
have `rsync` installed.

Installation
------------
Pypush can be installed using `pip`:

    pip install pypush

Or you can use `easy_install`:

    easy_install pypush

Usage
-----
```
usage: pypush [-h] [-q] [-v] [-s] [-i] [-e] [-a] [-p PORT] [-k] [--version]
              user@hostname dest

Continuously push changes in the current directory to a remote server. If this
is a Git/Mercurial directory, files that are ignored by Git/Mercurial will not
be pushed.

positional arguments:
  user@hostname         the remote machine (and optional user name) to login
                        to
  dest                  the path to the remote directory to push changes to

optional arguments:
  -h, --help            show this help message and exit
  -q, --quiet           quiet mode - do not show output whenever a file
                        changes
  -v, --verbose         verbose mode - run rsync in verbose mode
  -s, --skip-init       skip the initial one-way sync performed on startup
  -i, --show-ignored    print output even when ignored files are created or
                        modified (this flag is overridden by quiet mode)
  -e, --exit-after      exit after the initial sync, i.e. do not monitor the
                        directory for changes
  -a, --include-all     do not ignore any files
  -p PORT, --port PORT  the SSH port to use
  -k, --keep-extra      keep files on the remote that do not exist locally
  --version             show program's version number and exit

WARNING: pypush only performs a one-way sync. If you make changes directly on
the remote machine, they may be overwritten at any time by changes made
locally.
```

Example:

	pypush viveksjain@myserver.com '~/www'

Stop pypush by pressing `Ctrl+C`.

Support/Contact
===============
[Open a new issue](https://github.com/viveksjain/pypush/issues/new) or email me
at [pypush@vivekja.in](mailto:pypush@vivekja.in).