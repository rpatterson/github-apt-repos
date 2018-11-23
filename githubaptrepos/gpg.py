"""
Sign Debian/Ubuntu apt repositories with GPG keys.

All GPG dependent functionality lives here.
"""

import os
import logging
import email.utils
import subprocess

import gnupg

from . import repo

logger = logging.getLogger('github-apt-repose')

gpg = gnupg.GPG()

gpg_group = repo.parser.add_argument_group(
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


def set_up_gpg_key(args, apt_repo=None, gpg=gpg):
    """
    Optionally lookup or generate the GPG key to sign the APT repository.
    """
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
                name_real, name_email = email.utils.parseaddr(gpg_user_id)
                generated = gpg.gen_key(
                    gpg.gen_key_input(
                        name_real=name_real, name_email=name_email))
                if not generated.fingerprint:
                    raise ValueError(
                        'APT repository signing key not generated')
                gpg_pub_key, = gpg.export_keys(gpg_user_id)
    else:
        gpg_pub_key, = gpg.scan_keys(gpg_pub_key)
        gpg_user_id = gpg_pub_key['uids'][0]

    return gpg_pub_key, gpg_user_id


def make_apt_repo(
        gpg_user_id=None, gpg_pub_key_src=None, dist_arch_dir=os.curdir,
        gpg=gpg):
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
