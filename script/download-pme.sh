#!/bin/bash -e

function help {
    echo "Args:"
    echo -e "latest \t download latest release from Maven Central"
    echo -e "snapshot [URL] \t download latest snapshot from Maven repository at [URL].\n\t\tBy default use repository at ci.commonjava.org"
}

if [[ "$#" == 0 ]]; then
    help
fi

if [[ "$1" == "latest" ]]; then
  BASE_URL="http://repo1.maven.org/maven2/org/commonjava/maven/ext/pom-manipulation-ext"
  curl -sLo metadata.xml "$BASE_URL/maven-metadata.xml"
  LATEST_VERSION=$(sed -n 's/ *<latest>\(.*\)<\/latest>/\1/p' metadata.xml)

  curl -Lo pom-manipulation-cli.jar "$BASE_URL/$LATEST_VERSION/pom-manipulation-ext-$LATEST_VERSION.jar"
  rm metadata.xml

  echo "Downloaded version $LATEST_VERSION from Maven Central."
fi

if [[ "$1" == "snapshot" ]]; then
  DEFAULT_REPO_URL="http://ci.commonjava.org:8180/api/hosted/local-deployments"
  if [[ -z "$2" ]]; then
    REPO_URL="$DEFAULT_REPO_URL"
  else
    REPO_URL="$2"
  fi

  BASE_URL="$REPO_URL/org/commonjava/maven/ext/pom-manipulation-cli"

  URL="$BASE_URL/maven-metadata.xml"
  curl -sLo metadata.xml "$URL"
  SNAPSHOT_VERSION=$(sed -n 's/ *<version>\(.*\)<\/version>/\1/p' metadata.xml | sort -r | head -n 1)

  if [[ -z "$SNAPSHOT_VERSION" ]]; then
    echo "Failed to download PME from repository at $REPO_URL"
    exit 1
  fi

  URL="$BASE_URL/$SNAPSHOT_VERSION/maven-metadata.xml"
  curl -sLo metadata.xml "$URL"
  FILE=pom-manipulation-cli-$(sed -n 's/ *<version>\(.*\)-SNAPSHOT<\/version>/\1/p' metadata.xml)-$(sed -n 's/ *<timestamp>\(.*\)<\/timestamp>/\1/p' metadata.xml)-$(sed -n 's/ *<buildNumber>\(.*\)<\/buildNumber>/\1/p' metadata.xml).jar

  URL="$BASE_URL/$SNAPSHOT_VERSION/$FILE"
  curl -Lo pom-manipulation-cli.jar "$URL"
  rm metadata.xml

  echo "Downloaded latest snapshot of $SNAPSHOT_VERSION from $URL"
fi
