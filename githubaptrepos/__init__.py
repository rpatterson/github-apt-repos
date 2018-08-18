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
    from urllib.parse import _ALWAYS_SAFE
except ImportError:
    from urllib import urlretrieve  # BBB Python 2
    from urllib import always_safe
    _ALWAYS_SAFE = frozenset(always_safe)

from apt import debfile

import gnupg

import github3


logger = logging.getLogger('github-apt-repos')

# The regular expression used to identify the dist of a `*.deb` package
# package-name-dist_version_arch.deb
DEB_BASENAME_RE = r'{package}([-_\.](?P<dist>.+)|)_{version}_{arch}'

GH_ORIGIN_URL_RE = re.compile(
    r'^(https://github.com/|git@github.com:)'
    r'(?P<gh_repo_path>(?P<gh_user>.+)/(?P<gh_repo>.+?))(.git|)$')

# Map APT repo files without extensions to their closes match
APT_EXTENSIONS = {
    'Packages': '.txt',
    'Release': '.txt',
    'InRelease': '.sig',
    'apt-add-repo': '.sh',
}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    '--deb-dir', dest='deb_dir', metavar='DIR',
    help='The directory that contains the `*.deb` files, or into which '
    'to download them (default: a temporary directory).')
parser.add_argument(
    '--apt-dir', dest='apt_dir', metavar='DIR',
    help='The directory in which to construct the `apt-dist-arch` APT '
    'repositories, (default: `--deb-dir`).')

gpg_group = parser.add_argument_group(
    title='GnuPG Options',
    description='Options controlling the GPG signing of the APT repository, '
    'provide only one.').add_mutually_exclusive_group()
gpg_group.add_argument(
    '--gpg-pub-key', dest='gpg_pub_key',
    help='The path to an exported GPG public key of the private key with '
    'which to sign the APT repository (default: if present, a previously '
    'generated key based on the `--repo-dir` GitHub repository).')
gpg_group.add_argument(
    '--gpg-user-id', dest='gpg_user_id',
    help='The GPG `user-id` of the key to sign the APT repository with '
    '(default: generate a user ID from the `--repo-dir` '
    'GitHub user/organization name and the repository name).')

gh_group = parser.add_argument_group(
    title='GitHub Options',
    description='Options controlling the interactions with GitHub. '
    'For automatic download of GitHub `*.deb` releases or uploading '
    'the APT repository to a GitHub release, either '
    '`--github-token` or `--github-user` is required.')
gh_auth_group = gh_group.add_mutually_exclusive_group()
gh_auth_group.add_argument(
    '--github-token', dest='gh_access_token', metavar='GITHUB_TOKEN',
    help='Your GitHub API access token: https://github.com/settings/tokens')
gh_auth_group.add_argument(
    '--github-user', dest='gh_user', metavar='GITHUB_USER',
    help='Your GitHub login user name.')
gh_group.add_argument(
    '--github-repo', metavar='GITHUB_REPO_PATH', dest='gh_repo',
    help="If given a GitHub repoitory's `username/repo` path, "
    "download the `*.deb` files from that repository's releases.")
gh_group.add_argument(
    '--github-apt-repo', metavar='GITHUB_REPO_PATH', dest='gh_apt_repo',
    help="The GitHub `username/repo` path of the repository who's releases "
    "the APT repositories will be uploaded to (default: --github-repo).")


def parse_repo_path(api, repo_path):
    """
    Lookup a GitHub repository from the API given a `user/repo` path.
    """
    if api is None or repo_path is None:
        return
    user_name, repo_name = repo_path.split('/', 1)
    return api.repository(user_name, repo_name)


def download_release_debs(repo, tag=None, deb_dir=os.curdir):
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

        dest = os.path.join(deb_dir, asset.name)
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
    return dist_arch_dirs


def make_apt_repo(
        gpg, gpg_user_id=None, gpg_pub_key_src=None, dist_arch_dir=os.curdir):
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

    # Generate the Release file
    with open(os.path.join(dist_arch_dir, 'Release'), 'w') as release:
        logger.info('Writing %r', release.name)
        subprocess.check_call(
            ['apt-ftparchive', 'release', dist_arch_dir],
            stdout=release)

    # Optionally sign the Release files
    if gpg_user_id is not None:
        in_release_path = os.path.join(dist_arch_dir, 'InRelease')
        release_gpg_path = os.path.join(dist_arch_dir, 'Release.gpg')
        with open(os.path.join(dist_arch_dir, 'Release')) as release:
            logger.info('Signing %r', in_release_path)
            signed = gpg.sign_file(
                release, keyid=gpg_user_id, output=in_release_path)
            if not signed.fingerprint:
                raise ValueError(
                    'Failed to sign the APT repository `InRelease` file')

            release.seek(0)
            logger.info('Signing %r', release_gpg_path)
            signed = gpg.sign_file(
                release, keyid=gpg_user_id,
                clearsign=False, detach=True, output=release_gpg_path)
            if not signed.fingerprint:
                raise ValueError(
                    'Failed to sign the APT repository `Release.gpg` file')

    # Optionally link the public key
    if gpg_pub_key_src is not None:
        gpg_pub_key_dst = os.path.join(
            dist_arch_dir, os.path.basename(gpg_pub_key_src))
        if not os.path.exists(gpg_pub_key_dst):
            logger.info('Linking the public key: %r', gpg_pub_key_dst)
            os.link(gpg_pub_key_src, gpg_pub_key_dst)


def get_github_repo_path(repo_dir=os.curdir, origin_url_re=GH_ORIGIN_URL_RE):
    """
    Get the GitHub `user/repo` repository path from a checkout's origin.
    """
    origin_url = subprocess.check_output(
        ['git', 'remote', 'get-url', 'origin']).strip()
    origin_match = origin_url_re.match(origin_url)
    if origin_match is None:
        raise ValueError(
            'Did not recognize origin remote URL '
            'as a GitHub remote: {0}'.format(origin_url))
    return origin_match.group('gh_repo_path')


def release_apt_repo(repo, apt_dir, dist_arch_dir, gpg_pub_key_basename=None):
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
                    basename=user_repo_basename,
                    gpg_pub_key_basename=gpg_pub_key_basename))
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

    ##########################################################################
    # First do as much option handling as possible to fail early             #
    ##########################################################################
    args = parser.parse_args()

    # Optionally sign into the GitHub API
    api = None
    if args.gh_access_token is not None:
        api = github3.login(token=args.gh_access_token)
    elif args.gh_user is not None:
        password = input('GitHub login password:')
        api = github3.login(username=args.gh_user, password=password)
    elif args.gh_repo is not None or args.gh_apt_repo is not None:
        parser.error(
            'Must give `--github-token` or `--github-user` '
            'if using `--github-repo` or `--github-apt-repo`')

    # Optionally determine the GitHub repositories
    gh_repo_path = args.gh_repo
    if gh_repo_path is None:
        # Try to get a repo path from a checkout in the current directory
        try:
            gh_repo_path = get_github_repo_path()
        except Exception:
            pass
    repo = apt_repo = parse_repo_path(api, gh_repo_path)
    if args.gh_apt_repo is not None:
        apt_repo = parse_repo_path(api, args.gh_apt_repo)

    # Optionally set up GPG for signing the APT repositories
    gpg = gnupg.GPG()
    gpg_pub_key = args.gpg_pub_key
    gpg_user_id = args.gpg_user_id
    if gpg_pub_key is None:
        if gpg_user_id is None and apt_repo is not None:
            gpg_user_id = (
                '{repo_name} {user_name} '
                '<{user_name}+{repo_name}@github.com>'.format(
                    user_name=apt_repo.owner.login, repo_name=apt_repo.name))

        if gpg_user_id is not None:
            gpg_pub_key = gpg.export_keys(gpg_user_id)
            if not gpg_pub_key:
                logger.info(
                    'Public key not found for %r, generating a new key',
                    gpg_user_id)
                name_real, name_email = email.utils.parseaddr(
                    'From: ' + gpg_user_id)
                generated = gpg.gen_key(
                    gpg.gen_key_input(
                        name_real=name_real, name_email=name_email))
                if not generated.fingerprint:
                    raise ValueError(
                        'APT repository signing key not generated')
                gpg_pub_key, = gpg.export_keys(gpg_user_id)
    else:
        gpg_pub_key, = gpg.scan_keys(gpg_pub_key)
        gpg_user_id = gpg_pub_key['user-id']

    ##########################################################################
    # Finally, do any mutating or longer running tasks                       #
    ##########################################################################
    try:
        # Set up working directories
        deb_dir = args.deb_dir
        if deb_dir is None:
            prefix = 'deb'
            if apt_repo is not None:
                prefix += '-{0}-{1}'.format(
                    apt_repo.owner.login, apt_repo.name)
            deb_dir = tempfile.mkdtemp(prefix=prefix)
        apt_dir = args.apt_dir
        if apt_dir is None:
            apt_dir = deb_dir

        # Download releases if the repo is given
        if repo is not None:
            download_release_debs(repo, deb_dir=deb_dir)

        # Groups the `*.deb` files by unique distribution and architecture.
        dist_arch_dirs = group_debs(deb_dir=deb_dir, apt_dir=apt_dir)

        gpg_pub_key_src = None
        if gpg_pub_key is not None:
            gpg_pub_key_dotted = ''.join([
                (char if char in _ALWAYS_SAFE else '.')
                for char in gpg_user_id
            ]) + '.pub.key'
            # Strip duplicate dots
            gpg_pub_key_basename = gpg_pub_key_dotted.replace('..', '.')
            while gpg_pub_key_basename != gpg_pub_key_dotted:
                gpg_pub_key_dotted = gpg_pub_key_basename
                gpg_pub_key_basename = gpg_pub_key_dotted.replace('..', '.')
            gpg_pub_key_src = os.path.join(apt_dir, gpg_pub_key_basename)
            if not os.path.exists(gpg_pub_key_src):
                logger.info('Writing public key: %s', gpg_pub_key_src)
                with open(gpg_pub_key_src, 'w') as gpg_pub_key_opened:
                    gpg_pub_key_opened.write(gpg_pub_key)

        for dist_arch_dir in dist_arch_dirs:
            make_apt_repo(gpg, gpg_user_id, gpg_pub_key_src, dist_arch_dir)

        if apt_repo is not None:
            for dist_arch_dir in dist_arch_dirs:
                release_apt_repo(
                    apt_repo, apt_dir, dist_arch_dir, gpg_pub_key_basename)

    finally:
        if args.deb_dir is None:
            shutil.rmtree(deb_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
