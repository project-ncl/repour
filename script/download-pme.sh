#!/bin/bash -e

function help {
    echo 'Args:'
    echo 'latest - to download latest release from Maven Central'
    echo 'snapshot - to download latest PME build from CI.'
}

if [ "$#" -ne 1 ]; then
    help
fi

if [[ "$1" == "latest" ]]; then
  URL=http://repo1.maven.org/maven2/org/commonjava/maven/ext/pom-manipulation-ext/maven-metadata.xml
  curl -sLo metadata.xml "$URL"
  LATEST_VERSION=$(sed -n 's/ *<latest>\(.*\)<\/latest>/\1/p' metadata.xml)
  #echo $LATEST_VERSION
  curl -Lo pom-manipulation-cli.jar "http://repo1.maven.org/maven2/org/commonjava/maven/ext/pom-manipulation-ext/$LATEST_VERSION/pom-manipulation-ext-$LATEST_VERSION.jar"
  rm metadata.xml
  echo "Downloaded PME $LATEST_VERSION from Maven Central."
fi

if [[ "$1" == "snapshot" ]]; then
  URL=http://ci.commonjava.org:8180/api/hosted/local-deployments/org/commonjava/maven/ext/pom-manipulation-cli/maven-metadata.xml
  curl -sLo metadata.xml "$URL"
  SNAPSHOT_VERSION=$(sed -n 's/ *<version>\(.*\)<\/version>/\1/p' metadata.xml | sort -r | head -n 1)
  #echo "Downloading latest build of PME $SNAPSHOT_VERSION"
  URL="http://ci.commonjava.org:8180/api/hosted/local-deployments/org/commonjava/maven/ext/pom-manipulation-cli/$SNAPSHOT_VERSION/maven-metadata.xml"
  curl -sLo metadata.xml "$URL"
  FILE=pom-manipulation-cli-$(sed -n 's/ *<version>\(.*\)-SNAPSHOT<\/version>/\1/p' metadata.xml)-$(sed -n 's/ *<timestamp>\(.*\)<\/timestamp>/\1/p' metadata.xml)-$(sed -n 's/ *<buildNumber>\(.*\)<\/buildNumber>/\1/p' metadata.xml).jar
  URL="http://ci.commonjava.org:8180/api/hosted/local-deployments/org/commonjava/maven/ext/pom-manipulation-cli/$SNAPSHOT_VERSION/$FILE"
  curl -Lo pom-manipulation-cli.jar "$URL"
  rm metadata.xml
  echo "Downloaded latest build of $SNAPSHOT_VERSION from:"
  echo "$URL"
fi
