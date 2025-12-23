#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/data}"
OUT_PATH="${OUT_PATH:-$ROOT_DIR/dist/symclatron_db.tar.gz}"

DATA_DIR_ABS="$(realpath -m "$DATA_DIR")"
OUT_PATH_ABS="$(mkdir -p "$(dirname "$OUT_PATH")" && cd "$(dirname "$OUT_PATH")" && printf '%s/%s\n' "$(pwd)" "$(basename "$OUT_PATH")")"

if [[ ! -d "$DATA_DIR_ABS" ]]; then
  echo "Error: data directory not found: $DATA_DIR_ABS" >&2
  echo "Tip: run 'symclatron setup' first (or set DATA_DIR=/path/to/data)." >&2
  exit 1
fi

echo "Building symclatron data bundle"
echo "  Source data dir: $DATA_DIR_ABS"
echo "  Output tarball:  $OUT_PATH_ABS"

if [[ -f "$OUT_PATH_ABS" ]]; then
  echo "Removing existing tarball: $OUT_PATH_ABS"
  rm -f "$OUT_PATH_ABS"
fi

# Create a tarball with the layout expected by `symclatron setup`:
#   symclatron_db/data/...
DATA_PARENT_DIR="$(dirname "$DATA_DIR_ABS")"
DATA_BASENAME="$(basename "$DATA_DIR_ABS")"

tar -C "$DATA_PARENT_DIR" \
  --transform "s,^${DATA_BASENAME}$,symclatron_db/data," \
  --transform "s,^${DATA_BASENAME}/,symclatron_db/data/," \
  -czf "$OUT_PATH_ABS" "$DATA_BASENAME"

echo "[OK] Wrote: $OUT_PATH_ABS"
echo "Contents sanity check (first 25 entries):"
set +o pipefail
tar -tzf "$OUT_PATH_ABS" | head -n 25
set -o pipefail
