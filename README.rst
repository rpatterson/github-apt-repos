=====================================================
github-apt-repos
=====================================================
Use GitHub releases as a Debian/Ubuntu apt repository
-----------------------------------------------------

Provides a ``github-apt-repos`` utility for building simple,
project-specific APT repositories without the overhead or build
requirements of other APT repository hosts such as `Launchpad PPAs`_
or the `openSUSE Build Service`_.  If your project's build process
produces ``*.deb`` releases, or have considered it, but found the
requirements of other APT repository host onerous, this may be for
you.

The ``github-apt-repos`` utility currently does roughly the following:

#. Download the ``*.deb`` files from the latest GitHub release for a
   ``git`` checkout from GitHub
#. Make an APT repository from the released ``*.deb`` files
#. Upload the APT repository to a special GitHub release which
   Debian/Ubuntu users can use to keep up-to-date.

Each phase is intended to be optional and incremental, re-using build
artifacts already present, so it can be integrated into your build
process.


Installation
------------

The ``github-apt-repos`` utility is intended to be used in a
Debian/Ubuntu build environment with the usual DPKG and APT build
tools.  Specifically it requires the following be installed::

  $ sudo apt install python-pip dpkg-dev apt-utils gpg

Since APT repositories require signing with GPG keys,
``github-apt-repos`` is intended to be run on a build machine with
normal access to the GPG private keys to be used to sign the
repository.  If no key is specified, ``github-apt-repos`` will
generate a new key for each project by default, so be sure to use it
in an environment where you can preserve and manage the private keys.

Finally, install the actual package and its dependencies::

  $ sudo pip install https://github.com/rpatterson/github-apt-repos.git


Usage
-----

Generally, run ``github-apt-repos`` inside the checkout of the GitHub
checkout of the repository whose releases you want to build and upload
an APT repository for.  Note that, the APT repository needs to be
updated whenever your project has a new release so you may want to
integrate it in your build and release process and you may want to pay
particular attention to the ``--apt-dir`` option argument.

See the builtin, CLI help for further details::

  $ github-apt-repos --help

For example, TODO


TODO
----

In general, I'm eager to accept contributions or feature requests
that will generalize things, make different phases optional, and in
general be more agnostic about specific build processes.  For example,
make GitHub optional, just build an APT repo from ``*.deb`` files.
Another example, don't depend on git at all and be able to build an
APT repository from any build of ``*.deb`` releases.

Other TODOs:

- Release to PyPI
- Dogfood ``*.deb`` releases hosted in an APT repository on GitHub
- Short CLI options?  I'm really not sure we should.
- GitHub CLI to automatically build the apt repo when the upstream fork adds a
  release tag

I'm also open to discussing other contributions and feature requests.
Send PR's freely.


.. _Launchpad PPAs: https://help.launchpad.net/Packaging/PPA
.. _openSUSE Build Service: https://build.opensuse.org/
