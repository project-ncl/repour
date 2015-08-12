#!/bin/bash

# Prepare the docker directory to be sent to the Docker server

set -eu

if [ -f "Dockerfile" ]
then
    set -x
    context="$(readlink -e .)"
    root="$(readlink -e ..)"
else
    set -x
    context="$(readlink -e docker/)"
    root="$(readlink -e .)"
fi
dest="$context/content.tar"

owner="--gid 1000 --gname repour --uid 1000 --uname repour"

chmod 600 "$context/.ssh/config"
bsdtar $owner -cf "$dest" -C "$root" "venv-freeze.txt" -C "$context" ".ssh/config"
git ls-files -z "repour/" | xargs -0 bsdtar $owner -rf "$dest" -C "$root"

{ set +x; } 2>/dev/null
echo "Done"
