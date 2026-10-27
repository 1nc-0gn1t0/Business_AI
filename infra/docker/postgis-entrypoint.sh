#!/bin/sh
set -eu
# Never start a changed glibc/PostGIS stack on unverified existing PGDATA.
# New data directories are marked only after all upstream init scripts succeed.
if [ -s "$PGDATA/PG_VERSION" ]; then
    if [ "$(cat "$PGDATA/PG_VERSION")" != 17 ] ||
       [ ! -f "$PGDATA/.business-ai-pg17-trixie-v1" ]; then
        echo 'Unverified existing PGDATA refused. Use encrypted dump/restore into a NEW volume; see docs/CONTAINER_UPGRADE.md.' >&2
        exit 64
    fi
fi
exec /usr/local/bin/docker-entrypoint.sh "$@"
