#!/bin/sh
base=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 2
exec bash "$base/.novel-kit/hooks/scene_gate.sh" "$@"
