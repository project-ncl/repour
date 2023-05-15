#!/bin/bash

function help {
    echo "Args:"
    echo -e "(version) \n\t download version (version) from Maven Central."
    echo -e "latest \n\t Download latest version from Maven Central."
    echo -e "snapshot [URL] \n\t download latest snapshot from Maven repository at [URL] (optional)."
    echo -e "\t By default use the repository at oss.sonatype.org"
    echo -e "snapshot-version [VERSION] [URL] \n\t download snapshot with [VERSION] from Maven repository at [URL] (optional)."
    echo -e "\t By default use the repository at oss.sonatype.org"
}

MAVEN_CENTRAL_BASE_URL="https://repo1.maven.org/maven2/org/commonjava/maven/ext/pom-manipulation-cli"

function downloadVersionFromCentral {
  curl --http1.1 -Is "$MAVEN_CENTRAL_BASE_URL/$1/" | grep -q "404 Not Found"
  if [[ $? == 1 ]]; then
    curl -Lo pom-manipulation-cli.jar "$MAVEN_CENTRAL_BASE_URL/$1/pom-manipulation-cli-$1.jar"
    curl -Lo jar.md5 "$MAVEN_CENTRAL_BASE_URL/$1/pom-manipulation-cli-$1.jar.md5"
    echo "Downloaded version $1 from Maven Central."
  else
    echo "Version $1 does not exist in Maven Central."
    exit 1
  fi
}

function downloadLatestVersionFromCentral {
  curl -sLo metadata.xml "$MAVEN_CENTRAL_BASE_URL/maven-metadata.xml"
  LATEST_VERSION=$(sed -n 's/ *<latest>\(.*\)<\/latest>/\1/p' metadata.xml)
  downloadVersionFromCentral $LATEST_VERSION
  rm metadata.xml
}

function downloadLatestSnapshot {
  DEFAULT_REPO_URL="https://oss.sonatype.org/content/repositories/snapshots"
  if [[ -z "$1" ]]; then
    REPO_URL="$DEFAULT_REPO_URL"
  else
    REPO_URL="$1"
  fi

  BASE_URL="$REPO_URL/org/commonjava/maven/ext/pom-manipulation-cli"

  URL="$BASE_URL/maven-metadata.xml"
  curl -sLo metadata.xml "$URL"
  SNAPSHOT_VERSION=$(sed -n 's/ *<latest>\(.*\)<\/latest>/\1/p' metadata.xml)

  if [[ -z "$SNAPSHOT_VERSION" ]]; then
    echo "Failed to download PME from repository at $REPO_URL"
    exit 1
  fi

  URL="$BASE_URL/$SNAPSHOT_VERSION/maven-metadata.xml"
  curl -sLo metadata.xml "$URL"

  FILE_SNAPSHOT_SUFFIX=$(sed -n 's/ *<version>\(.*\)-SNAPSHOT<\/version>/\1/p' metadata.xml)-$(sed -n 's/ *<timestamp>\(.*\)<\/timestamp>/\1/p' metadata.xml)-$(sed -n 's/ *<buildNumber>\(.*\)<\/buildNumber>/\1/p' metadata.xml)
  if [[ "$FILE_SNAPSHOT_SUFFIX" == "--" ]]; then
    FILE_SNAPSHOT_SUFFIX=$SNAPSHOT_VERSION
  fi

  FILE="pom-manipulation-cli-$FILE_SNAPSHOT_SUFFIX.jar"
  URL="$BASE_URL/$SNAPSHOT_VERSION/$FILE"
  curl -Lo pom-manipulation-cli.jar "$URL"
  curl -Lo jar.md5 "$URL.md5"
  rm metadata.xml

  echo "Downloaded latest snapshot of $SNAPSHOT_VERSION from $URL"
}

function downloadSnapshotWithVersion {
  DEFAULT_REPO_URL="https://oss.sonatype.org/content/repositories/snapshots"
  if [[ -z "$1" ]]; then
    echo "SNAPSHOT version is not specified."
  else
    SNAPSHOT_VERSION="$1"
  fi
  if [[ -z "$2" ]]; then
    REPO_URL="$DEFAULT_REPO_URL"
  else
    REPO_URL="$2"
  fi

  BASE_URL="$REPO_URL/org/commonjava/maven/ext/pom-manipulation-cli"
  curl --http1.1 -Is "$BASE_URL/$SNAPSHOT_VERSION/" | grep -q "404 Not Found"
  if [[ $? == 0 ]]; then
    echo "PME snapshot $SNAPSHOT_VERSION does not exist at $BASE_URL/$SNAPSHOT_VERSION."
    exit 1
  fi

  URL="$BASE_URL/$SNAPSHOT_VERSION/maven-metadata.xml"
  curl -sLo metadata.xml "$URL"

  FILE_SNAPSHOT_SUFFIX=$(sed -n 's/ *<version>\(.*\)-SNAPSHOT<\/version>/\1/p' metadata.xml)-$(sed -n 's/ *<timestamp>\(.*\)<\/timestamp>/\1/p' metadata.xml)-$(sed -n 's/ *<buildNumber>\(.*\)<\/buildNumber>/\1/p' metadata.xml)
  if [[ "$FILE_SNAPSHOT_SUFFIX" == "--" ]]; then
    FILE_SNAPSHOT_SUFFIX=$SNAPSHOT_VERSION
  fi

  FILE="pom-manipulation-cli-$FILE_SNAPSHOT_SUFFIX.jar"
  URL="$BASE_URL/$SNAPSHOT_VERSION/$FILE"
  curl -Lo pom-manipulation-cli.jar "$URL"
  curl -Lo jar.md5 "$URL.md5"
  rm metadata.xml

  echo "Downloaded $SNAPSHOT_VERSION snapshot from $URL"
}

function verify_md5() {
    local md5_jar_dl=$(md5sum pom-manipulation-cli.jar | awk '{ print $1 }')
    local real_md5=$(cat jar.md5)

    if [[ "${md5_jar_dl}" != "${real_md5}" ]]; then
        echo "======================"
        echo "Mismatch in jar downloaded and its md5. Aborting"
        echo "======================"
        exit 1
    else
        echo "md5 of jar verified!"
    fi
}

if [[ "$#" == 0 ]]; then
  help
elif [[ "$1" == "snapshot" ]]; then
  downloadLatestSnapshot $2
elif [[ "$1" == "snapshot-version" ]]; then
  downloadSnapshotWithVersion $2 $3
elif [[ "$1" == "latest" ]]; then
  downloadLatestVersionFromCentral
else
  downloadVersionFromCentral $1
fi

verify_md5
