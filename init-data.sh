#!/bin/sh
set -eu
if [ "${RETROPORT_PLAYER:-0}" != 1 ]; then
    chown "${PUID:-911}:${PGID:-911}" /settings /collections /library/Games /operator-cores
fi
