#!/usr/bin/env python
"""
Create Debian/Ubuntu apt repositories from GitHub releases.
"""

import os
import tempfile
import email.utils
import shutil
import logging

from . import utils

logger = logging.getLogger('github-apt-repos')


def main():
    """
    Download all release deb assets, build and upload APT repos.
    """
    from . import gpg
    from . import github
    from . import repo

    logging.basicConfig(level=logging.INFO)

    ##########################################################################
    # First do as much option handling as possible to fail early             #
    ##########################################################################
    args = repo.parser.parse_args()

    # Optionally sign into the GitHub API
    api = github.login(args)

    # Optionally determine the GitHub repositories
    gh_repo_path = args.gh_repo
    if gh_repo_path is None:
        # Try to get a repo path from a checkout in the current directory
        try:
            gh_repo_path = github.get_github_repo_path()
        except Exception:
            pass
    deb_repo = apt_repo = github.parse_repo_path(api, gh_repo_path)
    if args.gh_apt_repo is not None:
        apt_repo = github.parse_repo_path(api, args.gh_apt_repo)

    # Optionally set up GPG for signing the APT repositories
    gpg_pub_key, gpg_user_id = gpg.set_up_gpg_key(args, apt_repo)

    ##########################################################################
    # Finally, do any mutating or longer running tasks                       #
    ##########################################################################
    try:
        # Set up working directories
        deb_dir = args.deb_dir
        if deb_dir is None:
            if deb_repo is None:
                raise ValueError(
                    'Must provide `--deb-dir` or a GitHub repository from '
                    'which to download release `*.deb` package files.')
            prefix = 'deb'
            if apt_repo is not None:
                prefix += '-{0}-{1}'.format(
                    apt_repo.owner.login, apt_repo.name)
            deb_dir = tempfile.mkdtemp(prefix=prefix)
        apt_dir = args.apt_dir
        if apt_dir is None:
            apt_dir = deb_dir

        # Download releases if the repo is given
        if deb_repo is not None:
            github.download_release_debs(deb_repo, deb_dir=deb_dir)

        # Groups the `*.deb` files by unique distribution and architecture.
        dist_arch_dirs = repo.group_debs(deb_dir=deb_dir, apt_dir=apt_dir)

        gpg_pub_key_src = None
        if gpg_pub_key is not None:
            gpg_pub_key_basename = utils.quote_dotted(
                email.utils.parseaddr(gpg_user_id)[1]) + '.pub.key'
            gpg_pub_key_src = os.path.join(apt_dir, gpg_pub_key_basename)
            if not os.path.exists(gpg_pub_key_src):
                logger.info('Writing public key: %s', gpg_pub_key_src)
                with open(gpg_pub_key_src, 'w') as gpg_pub_key_opened:
                    gpg_pub_key_opened.write(gpg_pub_key)

        for dist_arch_dir in dist_arch_dirs:
            gpg.make_apt_repo(gpg_user_id, gpg_pub_key_src, dist_arch_dir)

        if apt_repo is not None:
            for dist_arch_dir in dist_arch_dirs:
                github.release_apt_repo(
                    apt_repo, apt_dir, dist_arch_dir, gpg_pub_key_basename)

    finally:
        if deb_dir is not None and args.deb_dir is None:
            # If using a temporary directory, be sure to clean it up
            shutil.rmtree(deb_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
