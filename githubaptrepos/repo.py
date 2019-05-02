"""
Create Debian/Ubuntu apt repositories from `*.deb` files.

The functionality here has minimal external dependencies.  For example, no GPG
or GitHub functionality.
"""

import os
import glob
import re
import logging
import argparse

from apt import debfile

logger = logging.getLogger('github-apt-repos')

# The regular expression used to identify the dist of a `*.deb` package
# package-name-dist_version_arch.deb
DEB_BASENAME_RE = r'{package}([-_\.](?P<dist>.+)|)_{version}_{arch}'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    '--deb-dir', dest='deb_dir', metavar='DIR',
    help='The directory that contains the `*.deb` files, or into which '
    'to download them (default: a temporary directory).')
parser.add_argument(
    '--apt-dir', dest='apt_dir', metavar='DIR',
    help='The directory in which to construct the `apt-dist-arch` APT '
    'repositories, (default: `--deb-dir`).')


def get_deb_dist_arch(deb, basename_re=DEB_BASENAME_RE):
    """
    Return the distribution and architecture for a `*.deb` file.

    The distribution is taken from what ever is left when the
    architecture, package name, and version are removed:

    package-name-dist_version_arch.deb
    """
    deb_pkg = debfile.DebPackage(deb)
    arch = deb_pkg['Architecture']
    package = deb_pkg['Package']
    version = deb_pkg['Version']
    deb_basename_match = re.match(
        DEB_BASENAME_RE.format(
            arch=arch, package=package, version=version),
        os.path.splitext(os.path.basename(deb))[0])
    if deb_basename_match is None:
        dist = None
    else:
        dist = deb_basename_match.group(2)
    return dist, arch


def group_debs(
        deb_dir=os.curdir, apt_dir=os.curdir,
        basename_re=DEB_BASENAME_RE):
    """
    Groups the `*.deb` files by unique distribution and architecture.

    These groups are suitable for generating an APT repository from.

    The `*.deb` files are hard linked into the grouping to support
    re-using previously downloaded `*.deb`s.
    """
    dist_arch_dirs = set()
    for deb in glob.glob(os.path.join(deb_dir, '*.deb')):
        dist, arch = get_deb_dist_arch(deb, basename_re)
        if dist is None:
            dist_arch_dir = os.path.join(apt_dir, arch)
        else:
            dist_arch_dir = os.path.join(apt_dir, dist, arch)
        try:  # BBB Python 2, use exist_ok=True under Python 3
            os.makedirs(dist_arch_dir)
        except OSError as exc:
            # Ignore existing dirs
            if exc.errno != 17:
                raise
        dist_arch_dirs.add(dist_arch_dir)
        deb_link = os.path.join(dist_arch_dir, os.path.basename(deb))
        if not os.path.exists(deb_link):
            logger.info('Linking: %r', deb_link)
            os.link(deb, deb_link)
    if not dist_arch_dirs:
        raise ValueError(
            'No `*.deb` package files found in {0}'.format(deb_dir))
    return dist_arch_dirs
