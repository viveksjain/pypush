from setuptools import setup, find_packages

setup(
	name = 'pypush',
	version = '1.3',
	description = 'Continuously push local changes to a remote server',
	author = 'Vivek Jain',
	author_email = 'pypush@vivekja.in',
	url = 'https://github.com/viveksjain/pypush',
	classifiers = [
		'Programming Language :: Python',
		'Environment :: Console',
		'Development Status :: 3 - Alpha',
		'Intended Audience :: Developers',
		'License :: OSI Approved :: MIT License',
		'Operating System :: MacOS :: MacOS X',
		'Operating System :: POSIX',
		'Operating System :: Unix',
		'Topic :: Internet',
		'Topic :: System',
		'Topic :: Utilities'
	],
	py_modules = ['pypush'],
	install_requires=['watchdog >= 0.8'],
	entry_points = {
		'console_scripts': ['pypush = pypush:main']
	}
)
