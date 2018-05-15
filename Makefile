# Use GitHub releases as a Debian/Ubuntu apt repository

SHELL = /usr/bin/env bash -o pipefail -O extglob

PKGS = /usr/bin/git /usr/bin/wget


## Top level targets

build: download-releases .github-repo.path
# Generate the apt repos from the debs
	make -C apt build

clean:
	make -C apt clean
	rm -rf latest latest.* download .github-repo.path


## Real targets

$(PKGS):
	sudo apt install git wget dpkg-dev apt-utils gpg

.github-repo.path: /usr/bin/git
	./bin/get-github-repo-path >.github-repo.path

# Download the latest releases
download-releases: /usr/bin/wget .github-repo.path
	./bin/download-latest-debs <.github-repo.path


## Makefile administrivia
.PHONY: build download-releases clean
