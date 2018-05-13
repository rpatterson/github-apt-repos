# Use GitHub releases as a Debian/Ubuntu apt repository

SHELL=/usr/bin/env bash -o pipefail

BIN_SCANPKGS = $(shell which dpkg-scanpackages)
BIN_GPG = $(shell which gpg)
PKGS = $(BIN_SCANPKGS) $(BIN_GPG)

# Get the GitHub user and repo path from the top
GH_REPO_PATH = $(shell cat ../../../.github-repo.path)
GH_USER = $(dir $(GH_REPO_PATH))
# Strip the trailing slash
GH_USER ::= $(GH_USER:%/=%)
GH_REPO = $(notdir $(GH_REPO_PATH))

APT_FILES = Packages.gz Release InRelease Release.gpg

## Top level targets

build: $(APT_FILES)

clean:
	rm -f $(APT_FILES)


## Real targets

$(PKGS):
	sudo apt install dpkg-dev apt-utils gpg

# Generate the Packages file from the releases
Packages.gz: $(BIN_SCANPKGS)
	dpkg-scanpackages -m .. /dev/null | gzip -9c > Packages.gz

# Generate the necessary `apt-secure` release files
Release: /usr/bin/apt-ftparchive Packages.gz
	apt-ftparchive release . >Release
InRelease: $(BIN_GPG) Release
	gpg --clearsign -o InRelease Release
Release.gpg: $(BIN_GPG) Release
	gpg -abs -o Release.gpg Release


## Makefile administrivia
.PHONY: build clean
