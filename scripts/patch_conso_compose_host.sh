#!/bin/sh
set -eu
cp /home/cineglonne/docker-compose.conso-api-only.yml /docker/conso_elec_node/docker-compose.yml
echo COMPOSE_PATCHED
if grep -q caddy /docker/conso_elec_node/docker-compose.yml; then
  echo STILL_HAS_CADDY
  exit 1
fi
echo NO_CADDY
wc -l /docker/conso_elec_node/docker-compose.yml
