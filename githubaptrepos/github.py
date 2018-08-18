"""
Use GitHub releases as Debian/Ubuntu apt repositories.

All GitHub dependent functionality lives here.
"""

import os
import stat
import re
import mimetypes
import logging
import subprocess

try:
    from urllib.request import urlretrieve
except ImportError:
    from urllib import urlretrieve  # BBB Python 2

import github3

from . import repo

logger = logging.getLogger('github-apt-repos')

# Map APT repo files without extensions to their closes match
APT_EXTENSIONS = {
    'Packages': '.txt',
    'Release': '.txt',
    'InRelease': '.sig',
    'apt-add-repo': '.sh',
}

GH_ORIGIN_URL_RE = re.compile(
    r'^(https://github.com/|git@github.com:)'
    r'(?P<gh_repo_path>(?P<gh_user>.+)/(?P<gh_repo>.+?))(.git|)$')

gh_group = repo.parser.add_argument_group(
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


def login(args):
    """
    Optionally sign into the GitHub API
    """
    api = None
    if args.gh_access_token is not None:
        api = github3.login(token=args.gh_access_token)
    elif args.gh_user is not None:
        password = input('GitHub login password:')
        api = github3.login(username=args.gh_user, password=password)
    elif args.gh_repo is not None or args.gh_apt_repo is not None:
        repo.parser.error(
            'Must give `--github-token` or `--github-user` '
            'if using `--github-repo` or `--github-apt-repo`')
    return api


def parse_repo_path(api, repo_path):
    """
    Lookup a GitHub repository from the API given a `user/repo` path.
    """
    if api is None or repo_path is None:
        return
    user_name, repo_name = repo_path.split('/', 1)
    return api.repository(user_name, repo_name)


def download_release_debs(deb_repo, tag=None, deb_dir=os.curdir):
    """
    Download all the `*.deb` assets from the release.

    Defaults to the latest release.
    """
    if tag is None:
        release = deb_repo.latest_release()
    else:
        release = deb_repo.release_from_tag(tag)

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


def release_apt_repo(
        apt_repo, apt_dir, dist_arch_dir, gpg_pub_key_basename=None):
    """
    Upload the APT repository as a GitHub release.
    """
    # Convert the dist+arch specific APT repo path to a GH-friendly tag
    dist_arch = os.path.relpath(dist_arch_dir, apt_dir)
    tag = 'apt-' + dist_arch.replace('/', '-')
    base_download_url = 'https://github.com/{0}/releases/download/{1}'.format(
        apt_repo.full_name, tag)
    user_repo_basename = apt_repo.owner.login + '-' + apt_repo.name

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
        release = apt_repo.release_from_tag(tag)
    except github3.exceptions.NotFoundError:
        name = 'Debian/Ubuntu APT repository for {0}'.format(dist_arch)
        with open(os.path.join(
                os.path.dirname(__file__), 'release-body.md')) as body_opened:
            # Generate the release body text
            body = body_opened.read().format(repo=apt_repo, tag=tag, name=name)
        logger.info('Creating new release: %s', tag)
        release = apt_repo.create_release(tag_name=tag, name=name, body=body)

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
