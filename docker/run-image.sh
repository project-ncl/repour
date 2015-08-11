#!/bin/bash

set -eu

die() {
    echo "$@"
    exit 1
}

[ -d "/mnt/repour/vol" ] || die "Set up /mnt/repour/vol (/config.yaml, /repour.key) first"

docker run --detach \
    --publish "7331:7331" \
    --name "repour" \
    --restart "always" \
    --volume "/mnt/repour/vol:/home/repour/vol" \
    "${1:-docker-registry.usersys.redhat.com}/project-ncl/repour:latest"
