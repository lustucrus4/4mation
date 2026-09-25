#!/bin/sh
set -eu
SCRIPT_HOST_PATH="${1:-/tmp/restore_nginx_host.sh}"
docker run --rm --privileged --pid=host --network host \
  -v "$SCRIPT_HOST_PATH:/restore.sh:ro" \
  alpine:3.20 \
  /bin/sh -ec 'apk add --no-cache util-linux >/dev/null; nsenter -t 1 -m -u -i -n -p -- sh /restore.sh'
