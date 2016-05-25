#!/bin/bash -e

cd /home/repour

USR_ID=1001
USR=$(getent passwd "$USR_ID" | cut -d: -f1)

function help {
  echo "Setup the environment by running commands as root"
  echo "and then execute the rest of the arguments as '$USR'."
  echo "Args:"
  echo " 1. Certificate setup - path to cert file as the first argument. Set to '-' to skip."
  echo "Rest of the argument line will be executed as '$USR'."
  exit
}

if [ "$#" -eq 0 ]; then
  help
fi

if [ "$1" != "-" ] && [ -f "$1" ];
then
  update-ca-trust force-enable
  cp $1 /etc/pki/ca-trust/source/anchors/
  update-ca-trust extract
else
  echo "Skipping certificate setup."
fi
shift

if [ "$#" -gt 0 ];
then
  echo "Executing '$@' as '$USR'."
  sudo -E -u "$USR" "$@"
fi
