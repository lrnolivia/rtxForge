#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ -e /run/.containerenv ]]; then
  exec distrobox-host-exec /usr/bin/python3 -B "$root/gui/rtxforge_gtk.py" "$@"
fi
exec /usr/bin/python3 -B "$root/gui/rtxforge_gtk.py" "$@"
