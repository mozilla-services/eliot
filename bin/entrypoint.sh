#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

if [ -z "$*" ]; then
    echo "usage: entrypoint.sh SERVICE"
    echo ""
    echo "Services:"
    grep -E '^[a-zA-Z0-9_-]+).*?## .*$$' /app/bin/entrypoint.sh \
        | grep -v grep \
        | sed -n 's/^\(.*\)) \(.*\)##\(.*\)/* \1:\3/p'
    exit 1
fi

SERVICE=$1
shift

case ${SERVICE} in
eliot)  ## Run Eliot service
    exec honcho -f /app/Procfile --no-prefix start
    ;;
bash)  ## Open a bash shell or run something else
    if [ -z "$*" ]; then
        bash
    else
        "$@"
    fi
    ;;
*)
    echo "Unknown service ${SERVICE}"
    exit 1
esac
