#!/bin/bash -e

WORK_DIR="/home/repour"
cd "$WORK_DIR"

USR_ID=1001
USR=$(getent passwd "$USR_ID" | cut -d: -f1)

./download-pme.sh "latest"

sudo -E -u "$USR" "./pid1.py" "./au.py" "python3" "-m" "repour" "run-container"
