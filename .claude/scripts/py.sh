#!/bin/sh
base=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 2
exec bash "$base/.novel-kit/scripts/py.sh" "$@"
