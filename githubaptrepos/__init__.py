#!/usr/bin/env python
"""
Create Debian/Ubuntu apt repositories from GitHub releases.
"""

import os
import stat
import glob
import re
import tempfile
import shutil
import logging
import subprocess
import mimetypes
import email.utils
import argparse

try:
    from urllib.request import urlretrieve
except ImportError:
    from urllib import urlretrieve  # BBB Python 2

from apt import debfile

import gnupg

import github3


logger = logging.getLogger('github-apt-repos')

# The regular expression used to identify the dist of a `*.deb` package
# package-name-dist_version_arch.deb
DEB_BASENAME_RE = r'{package}([-_\.](?P<dist>.+)|)_{version}_{arch}'

GH_ORIGIN_URL_RE = re.compile(
    r'^(https://github.com/|git@github.com:)'
    r'(?P<gh_user>.+)/(?P<gh_repo>.+?)(.git|)$')

# Map APT repo files without extensions to their closes match
APT_EXTENSIONS = {
    'Packages': '.txt',
    'Release': '.txt',
    'InRelease': '.sig',
    'apt-add-repo': '.sh',
}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    '--repo-dir', dest='repo_dir', default=os.curdir,
    help='The git checkout directory of the repository '
    'whose releases to make an APT repository for')
parser.add_argument(
    '--apt-dir', dest='apt_dir',
    help='The directory in which to download the `*.deb` files '
    'and construct APT repositories, defaults to a temporary directory')
parser.add_argument(
    '--github-apt-repo', dest='gh_apt_repo',
    help="If given a GitHub repoitory's `username/repo` path, "
    "the APT repositories will be uploaded to `apt-dist-arch` releases")

gpg_group = parser.add_mutually_exclusive_group()
gpg_group.add_argument(
    '--gpg-pub-key', dest='gpg_pub_key',
    help='The path to an exported GPG public key '
    'to sign the APT repository')
gpg_group.add_argument(
    '--gpg-user-id', dest='gpg_user_id',
    help='The GPG `user-id` of the key to sign the APT repository')

gh_group = parser.add_mutually_exclusive_group(required=True)
gh_group.add_argument(
    '--github-token', dest='gh_access_token',
    help='Your GitHub API access token: https://github.com/settings/tokens')
gh_group.add_argument(
    '--github-user', dest='gh_user',
    help='Your GitHub login user name')


def download_release_debs(repo, tag=None, apt_dir=os.curdir):
    """
    Download all the `*.deb` assets from the release.

    Defaults to the latest release.
    """
    if tag is None:
        release = repo.latest_release()
    else:
        release = repo.release_from_tag(tag)

    assets = []
    for asset in release.assets():
        name, ext = os.path.splitext(asset.name)
        if ext.lower() != '.deb':
            # Ignore all assets that aren't `*.deb` packages
            continue

        dest = os.path.join(apt_dir, asset.name)
        if not os.path.exists(dest):
            logger.info(
                'Downloading release asset: %s', asset.browser_download_url)
            urlretrieve(asset.browser_download_url, dest)
        else:
            logger.info(
                'Re-using previously downloaded `*.deb` file: %r', dest)

        assets.append(asset)

    return assets


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
    dist = deb_basename_match.group(2)
    return dist, arch


def group_debs(apt_dir=os.curdir, basename_re=DEB_BASENAME_RE):
    """
    Groups the `*.deb` files by unique distribution and architecture.

    These groups are suitable for generating an APT repository from.

    The `*.deb` files are hard linked into the grouping to support
    re-using previously downloaded `*.deb`s.
    """
    dist_arch_dirs = set()
    for deb in glob.glob(os.path.join(apt_dir, '*.deb')):
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
    return dist_arch_dirs


def make_apt_repo(gpg, gpg_user_id, gpg_pub_key_src, dist_arch_dir=os.curdir):
    """
    Make an APT repository from a directory containing `*.deb` files.

    The repository will cause unexpected packages to be downloaded by
    apt unless the debs in this directory are only of one unique
    distribution and architecture combination, such as the grouping
    done by `group_debs()`.
    """
    # Generate the Packages file
    with open(os.path.join(dist_arch_dir, 'Packages'), 'w') as packages:
        logger.info('Writing %r', packages.name)
        subprocess.check_call(
            ['dpkg-scanpackages', '-m', os.curdir, '/dev/null'],
            cwd=dist_arch_dir, stdout=packages)

    # Make and sign the Release files
    with open(os.path.join(dist_arch_dir, 'Release'), 'w') as release:
        logger.info('Writing %r', release.name)
        subprocess.check_call(
            ['apt-ftparchive', 'release', dist_arch_dir],
            stdout=release)
    in_release_path = os.path.join(dist_arch_dir, 'InRelease')
    release_gpg_path = os.path.join(dist_arch_dir, 'Release.gpg')
    with open(os.path.join(dist_arch_dir, 'Release')) as release:
        logger.info('Signing %r', in_release_path)
        gpg.sign_file(release, keyid=gpg_user_id, output=in_release_path)

        release.seek(0)
        logger.info('Signing %r', release_gpg_path)
        gpg.sign_file(
            release, keyid=gpg_user_id,
            clearsign=False, detach=True, output=release_gpg_path)

    # Link the public key
    gpg_pub_key_dst = os.path.join(
        dist_arch_dir, os.path.basename(gpg_pub_key_src))
    if not os.path.exists(gpg_pub_key_dst):
        logger.info('Linking the public key: %r', gpg_pub_key_dst)
        os.link(gpg_pub_key_src, gpg_pub_key_dst)


def get_github_repo(api, repo_dir=os.curdir, origin_url_re=GH_ORIGIN_URL_RE):
    """
    Get the GitHub API object for the `origin` of the repository.
    """
    origin_url = subprocess.check_output(
        ['git', 'remote', 'get-url', 'origin']).strip()
    origin_match = origin_url_re.match(origin_url)
    if origin_match is None:
        raise ValueError(
            'Did not recognize origin remote URL '
            'as a GitHub remote: {0}'.format(origin_url))
    return api.repository(
        origin_match.group('gh_user'), origin_match.group('gh_repo'))


def release_apt_repo(repo, apt_dir, dist_arch_dir):
    """
    Upload the APT repository as a GitHub release.
    """
    # Convert the dist+arch specific APT repo path to a GH-friendly tag
    dist_arch = os.path.relpath(dist_arch_dir, apt_dir)
    tag = 'apt-' + dist_arch.replace('/', '-')
    base_download_url = 'https://github.com/{0}/releases/download/{1}'.format(
        repo.full_name, tag)
    user_repo_basename = repo.owner.login + '-' + repo.name

    # Generate the APT repo sources.list
    apt_add_path = os.path.join(dist_arch_dir, user_repo_basename + '.list')
    with open(os.path.join(
            os.path.dirname(__file__), 'sources.list')) as apt_add_repo_tmpl:
        with open(apt_add_path, 'w') as apt_add_repo:
            logger.info(
                'Writing the APT repository source: %r', apt_add_path)
            apt_add_repo.write(
                apt_add_repo_tmpl.read().format(
                    base_download_url=base_download_url,
                    basename=user_repo_basename))

    # Generate the APT repo install script
    apt_add_path = os.path.join(dist_arch_dir, 'apt-add-repo')
    with open(os.path.join(
            os.path.dirname(__file__), 'apt-add-repo')) as apt_add_repo_tmpl:
        with open(apt_add_path, 'w') as apt_add_repo:
            logger.info(
                'Writing the APT repository install script: %r', apt_add_path)
            apt_add_repo.write(
                apt_add_repo_tmpl.read().format(
                    base_download_url=base_download_url,
                    basename=user_repo_basename))
    os.chmod(
        apt_add_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
        stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | stat.S_IROTH |
        stat.S_IXOTH)

    # Get or create the corresponding GH release
    try:
        release = repo.release_from_tag(tag)
    except github3.exceptions.NotFoundError:
        name = 'Debian/Ubuntu APT repository for {0}'.format(dist_arch)
        with open(os.path.join(
                os.path.dirname(__file__), 'release-body.md')) as body_opened:
            # Generate the release body text
            body = body_opened.read().format(repo=repo, tag=tag, name=name)
        logger.info('Creating new release: %s', tag)
        release = repo.create_release(tag_name=tag, name=name, body=body)

    # Add or update (delete and re-add) the assets
    assets = {asset.name: asset for asset in release.assets()}
    for asset_name in os.listdir(dist_arch_dir):
        asset = assets.get(asset_name)
        if asset is not None:
            # Delete any assets that correspond to one in the repo
            logger.info(
                'Deleting existing release asset: %s',
                asset.browser_download_url)
            asset.delete()

        # Guess the most appropriate MIME type
        path = os.path.join(dist_arch_dir, asset_name)
        content_type, encoding = mimetypes.guess_type(asset_name)
        if content_type is None:
            content_type, encoding = mimetypes.guess_type(
                asset_name + APT_EXTENSIONS.get(asset_name, '.txt'))

        logger.info(
            'Uploading release asset: %s', path)
        with open(path) as asset_opened:
            asset = release.upload_asset(
                content_type=content_type, name=asset_name,
                asset=asset_opened)


def main():
    """
    Download all release deb assets, build and upload APT repos.
    """
    logging.basicConfig(level=logging.INFO)
    args = parser.parse_args()

    # Login to the GitHub API
    if args.gh_access_token:
        api = github3.login(token=args.gh_access_token)
    else:
        password = input('GitHub login password:')
        api = github3.login(username=args.gh_user, password=password)

    repo = get_github_repo(api, args.repo_dir)

    gpg = gnupg.GPG()
    gpg_pub_key = args.gpg_pub_key
    gpg_user_id = args.gpg_user_id
    if gpg_pub_key is None:
        if gpg_user_id is None:
            gpg_user_id = (
                '{repo_name} {user_name} '
                '<{user_name}+{repo_name}@github.com>'.format(
                    user_name=repo.owner.login, repo_name=repo.name))

        gpg_pub_key = gpg.export_keys(gpg_user_id)
        if not gpg_pub_key:
            logger.info(
                'Public key not found for %r, generating a new key',
                gpg_user_id)
            name_real, name_email = email.utils.parseaddr(
                'From: ' + gpg_user_id)
            gpg.gen_key(
                gpg.gen_key_input(name_real=name_real, name_email=name_email))
            gpg_pub_key, = gpg.export_keys(gpg_user_id)
    else:
        gpg_pub_key, = gpg.scan_keys(gpg_pub_key)
        gpg_user_id = gpg_pub_key['user-id']

    apt_dir = args.apt_dir
    if apt_dir is None:
        apt_dir = tempfile.mkdtemp(
            prefix='apt-{0}-{1}'.format(repo.owner.login, repo.name))
    try:

        gpg_pub_key_src = os.path.join(
            apt_dir, '{0}-{1}.pub.key'.format(repo.owner.login, repo.name))
        if not os.path.exists(gpg_pub_key_src):
            logger.info('Writing public key: %s', gpg_pub_key_src)
            with open(gpg_pub_key_src, 'w') as gpg_pub_key_opened:
                gpg_pub_key_opened.write(gpg_pub_key)

        # TODO Support using locally built debs
        download_release_debs(repo, apt_dir=apt_dir)

        dist_arch_dirs = group_debs(apt_dir=apt_dir)
        for dist_arch_dir in dist_arch_dirs:
            make_apt_repo(gpg, gpg_user_id, gpg_pub_key_src, dist_arch_dir)

        if args.gh_apt_repo:
            for dist_arch_dir in dist_arch_dirs:
                release_apt_repo(
                    api.repository(*args.gh_apt_repo.split('/', 1)),
                    apt_dir, dist_arch_dir)

    finally:
        if args.apt_dir is None:
            shutil.rmtree(apt_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
