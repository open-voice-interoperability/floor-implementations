#!/usr/bin/env bash
# Refresh vendored Floor API + stock mock from a canonical FLOOR checkout (optional).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLOOR_SRC="${FLOOR_SRC:-$ROOT/../FLOOR}"
if [[ ! -d "$FLOOR_SRC/src" ]]; then
  echo "Expected FLOOR repo at: $FLOOR_SRC (set FLOOR_SRC to override)" >&2
  exit 1
fi
rm -rf "$ROOT/services/floor_api/src" "$ROOT/services/stock_mock/examples"
cp -R "$FLOOR_SRC/src" "$ROOT/services/floor_api/"
cp -R "$FLOOR_SRC/examples" "$ROOT/services/stock_mock/"
echo "Synced from $FLOOR_SRC — run: docker compose -f \"$ROOT/docker-compose.yml\" build --no-cache"
