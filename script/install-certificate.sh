#!/bin/bash -e

function help {
  echo "Provide path to cert file as the first argument."
  echo "Rest of the argument line will be exec'd."
  exit
}

if [ "$#" -eq 0 ]; then
  help
fi

if [ -f "$1" ];
then
  update-ca-trust force-enable
  cp $1 /etc/pki/ca-trust/source/anchors/
  update-ca-trust extract
else
  echo "No such file: $1"
fi

if [ "$#" -gt 1 ];
then
  shift
  echo "Executing $@"
  exec "$@"
fi
