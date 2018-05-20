# {name}

To add this APT repository to your `/etc/apt/sources.list.d`, add the
signing GPG key, and update the package DB, run the following command:

    $ curl -L https://github.com/{repo}/releases/download/{tag}/apt-add-repo | sh

You can then use APT to install any of the packages in this repo and
to automatically keep them up-to-date going forward
