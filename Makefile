# Set up a isolated environment and install into it

.PHONY: build
build: .venv/bin/github-apt-repos

.venv:
	virtualenv .

.venv/bin/github-apt-repos: .venv
	.venv/bin/pip install -U --upgrade-strategy=eager -e .
