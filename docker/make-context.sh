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

bsdtar -cf "$dest" -C "$root" "config.yaml" "venv-freeze.txt" -C "$context" ".ssh/config" ".ssh/repour"
bsdtar -rf "$dest" -C "$root" --include "*.py" "repour/"

{ set +x; } 2>/dev/null
echo "Done"
