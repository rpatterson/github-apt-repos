# Use GitHub releases as a Debian/Ubuntu apt repository

SHELL = /usr/bin/env bash -o pipefail -O extglob

BIN_GIT = $(shell which git)
BIN_WGET = $(shell which wget)
PKGS = $(BIN_GIT) $(BIN_WGET)

## Top level targets

build: download-releases .github-repo.path
	make -C releases/download/apt build

clean:
	make -C releases/download/apt clean
	rm -rf latest latest.* releases/download/!(apt) .github-repo.path


## Real targets

$(PKGS):
	sudo apt install git wget

.github-repo.path: $(BIN_GIT)
	./bin/get-github-repo-path >.github-repo.path

# Download the latest releases
download-releases: $(BIN_WGET) .github-repo.path
	./bin/download-latest-debs <.github-repo.path


## Makefile administrivia
.PHONY: build download-releases
