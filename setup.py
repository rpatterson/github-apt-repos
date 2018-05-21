from setuptools import setup, find_packages

version = '0.1'

setup(name='github-apt-repos',
      version=version,
      description="Host Debian/Ubuntu APT repositories on GitHub releases.",
      long_description=open('README.rst').read(),
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Natural Language :: English',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Topic :: Software Development',
          'Topic :: Software Development :: Build Tools',
          'Topic :: Software Development :: Version Control :: Git',
          'Topic :: System :: Software Distribution',
          'Topic :: Utilities',
      ],
      keywords='git github apt debian ubuntu deb dpkg',
      author='Ross Patterson',
      author_email='me@rpatterson.net',
      url='https://github.com/rpatterson/github-apt-repos',
      license='GPL',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'python-gnupg',
          'github3.py',
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
