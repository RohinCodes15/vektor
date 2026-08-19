#!/bin/sh
# Volumes are usually mounted owned by root. Give the data directory to the unprivileged user, then drop root.
set -eu
DATA_DIR="${VEKTOR_DATA_DIR:-/data}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  chown vektor:vektor "$DATA_DIR"
  exec setpriv --reuid=vektor --regid=vektor --init-groups "$@"
fi
exec "$@"
