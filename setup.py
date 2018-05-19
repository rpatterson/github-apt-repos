from setuptools import setup, find_packages
import sys, os

version = '0.1'

setup(name='github-apt-repos',
      version=version,
      description="Host Debian/Ubuntu APT repositories on GitHub releases.",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='git github apt debian ubuntu deb dpkg',
      author='Ross Patterson',
      author_email='me@rpatterson.net',
      url='https://github.com/rpatterson/github-apt-repos',
      license='GPL',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
