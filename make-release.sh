#!/usr/bin/env bash
github-apt-repos \
--github-repo feverscreen/feverscreen \
--github-token ${GITHUB_TOKEN} \
--github-apt-repo feverscreen/fs-apt-source \
--gpg-pub-key ~/public.key \
--github-delete-existing
