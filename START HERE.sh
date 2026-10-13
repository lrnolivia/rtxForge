#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ -e /run/.containerenv ]]; then
  exec distrobox-host-exec /usr/bin/python3 -B "$root/scripts/engine_cli.py" "$@"
fi
exec python3 -B "$root/scripts/engine_cli.py" "$@"
