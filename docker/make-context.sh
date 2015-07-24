#!/bin/bash

# Prepare the docker directory to be sent to the Docker server

set -eu

if [ -f "Dockerfile" ]
then
    set -x
    src=".."
else
    set -x
    src="."
fi
dest="docker/content.tar"

cd "$src"

bsdtar -cf "$dest" "config.yaml"
find "repour" -type f -name '*.py' -print0 | xargs -0 bsdtar -rf "$dest"

{ set +x; } 2>/dev/null
echo "Done"
