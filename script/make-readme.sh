#!/bin/bash

README_FILE_PATH="./README.asciidoc"

if ! [ -x "$(command -v asciidoc)" ]; then
  echo "'asciidoc' is not installed. Try 'dnf install asciidoc'."
  exit 1
fi

BRANCH=$(git describe --all --exact-match HEAD)

if [ -z "$BRANCH" ]; then
  BRANCH="HEAD"
fi

COMMIT_ID=$(git rev-parse --short "$BRANCH")

if [ -z "$COMMIT_ID" ]; then
  echo "Could not parse git revision '$BRANCH'."
  exit 1
fi

asciidoc -a repourRevision="$BRANCH ($COMMIT_ID)" "$README_FILE_PATH"
