# Use GitHub releases as a Debian/Ubuntu apt repository

SHELL=/usr/bin/env bash -o pipefail -O extglob

BIN_SCANPKGS = $(shell which dpkg-scanpackages)
BIN_GPG = $(shell which gpg)
BIN_FTPARCHIVE = $(shell which apt-ftparchive)
PKGS = $(BIN_SCANPKGS) $(BIN_GPG) $(BIN_FTPARCHIVE)

# Get the GitHub user and repo path from the top
ifneq ("$(wildcard ../.github-repo.path)","")
GH_REPO_PATH = $(shell cat ../.github-repo.path)
GH_USER = $(dir $(GH_REPO_PATH))
# Strip the trailing slash
GH_USER ::= $(GH_USER:%/=%)
GH_REPO = $(notdir $(GH_REPO_PATH))

# Form a GPG user id specific to the repo
GPG_USER_ID = $(GH_REPO) $(GH_USER) <$(GH_USER)+$(GH_REPO)@github.com>
GPG_PUB_KEY = $(GH_USER)-$(GH_REPO).gpg.pub
endif

## Top level targets

build: $(BIN_SCANPKGS) $(BIN_FTPARCHIVE) $(BIN_GPG) $(GPG_PUB_KEY)
# Generate the apt repos from the debs
	../bin/make-apt-repos  ../download \
		"$(GPG_USER_ID)" "$(GPG_PUB_KEY)"

clean:
	rm -rf !(Makefile)


## Real targets

$(PKGS):
	sudo apt install dpkg-dev apt-utils gpg

$(GPG_PUB_KEY): $(BIN_GPG)
# Generate a new key if we don't already have a secret key for the ID
	gpg --list-secret-keys "$(GPG_USER_ID)" || \
		gpg --quick-generate-key "$(GPG_USER_ID)"
# Export the public key
	gpg --armor --output $(GPG_PUB_KEY) --export "$(GPG_USER_ID)"


## Makefile administrivia
.PHONY: build clean
