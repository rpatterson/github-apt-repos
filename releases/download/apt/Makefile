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

# Form a GPG user id specific to the repo
GPG_USER_ID = $(GH_REPO) $(GH_USER) <$(GH_USER)+$(GH_REPO)@github.com>
GPG_PUB_KEY = $(GH_USER)-$(GH_REPO).gpg.pub

APT_FILES = Packages.gz Release InRelease Release.gpg

## Top level targets

build: $(APT_FILES)

clean:
ifdef GH_USER
	rm -f $(GPG_PUB_KEY)
endif
	rm -f $(APT_FILES)


## Real targets

$(PKGS):
	sudo apt install dpkg-dev apt-utils gpg

# Generate the Packages file from the releases
Packages.gz: $(BIN_SCANPKGS)
	dpkg-scanpackages -m .. /dev/null | gzip -9c > Packages.gz

$(GPG_PUB_KEY): $(BIN_GPG)
# Generate a new key if we don't already have a secret key for the ID
	gpg --list-secret-keys "$(GPG_USER_ID)" || \
		gpg --quick-generate-key "$(GPG_USER_ID)"
# Export the public key
	gpg --armor --output $(GPG_PUB_KEY) --export "$(GPG_USER_ID)"

# Generate the necessary `apt-secure` release files
Release: /usr/bin/apt-ftparchive Packages.gz
	apt-ftparchive release . >Release
InRelease: $(BIN_GPG) $(GPG_PUB_KEY) Release 
	gpg -u "$(GPG_USER_ID)" --clearsign -o InRelease Release
Release.gpg: $(BIN_GPG) $(GPG_PUB_KEY) Release
	gpg -u "$(GPG_USER_ID)" -abs -o Release.gpg Release


## Makefile administrivia
.PHONY: build clean
