#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITHUB_REPO="${GITHUB_REPO:-NeLLi-team/symclatron}"

TAG_OR_VERSION="${1:-db-latest}"

TAG="$TAG_OR_VERSION"
if [[ "$TAG" != v* && "$TAG" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+.*$ ]]; then
  TAG="v$TAG"
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh (GitHub CLI) is required. Install from https://cli.github.com/ and run 'gh auth login'." >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh is not authenticated. Run 'gh auth login'." >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/data" ]]; then
  echo "Error: data directory not found at: $ROOT_DIR/data" >&2
  echo "Tip: run 'symclatron setup' first (or set up the data/ directory) before publishing." >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/dist"
MANIFEST_PATH="$ROOT_DIR/dist/symclatron_db.manifest.json"

python - <<'PY' "$ROOT_DIR/data" "$MANIFEST_PATH"
import json
import pathlib
import sys

data_root = pathlib.Path(sys.argv[1]).resolve()
out_path = pathlib.Path(sys.argv[2]).resolve()

files = []
for path in sorted(data_root.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(data_root).as_posix()
    stat = path.stat()
    files.append({"path": rel, "size": stat.st_size})

payload = {"schema": 1, "root": "data", "files": files}
out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"[OK] Wrote manifest: {out_path}")
PY

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
REMOTE_MANIFEST_PATH="$TMPDIR/symclatron_db.manifest.json"

if ! gh release view "$TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
  echo "GitHub release not found for ${TAG}; creating it."
  gh release create "$TAG" --repo "$GITHUB_REPO" --title "$TAG" --generate-notes
fi

if gh release download "$TAG" --repo "$GITHUB_REPO" --dir "$TMPDIR" --pattern "symclatron_db.manifest.json" >/dev/null 2>&1; then
  if cmp -s "$MANIFEST_PATH" "$REMOTE_MANIFEST_PATH"; then
    echo "[OK] Data bundle unchanged; reusing existing GitHub asset for ${TAG}."
    echo "Download URL: https://github.com/${GITHUB_REPO}/releases/download/${TAG}/symclatron_db.tar.gz"
    exit 0
  fi
else
  echo "Remote manifest not found for ${TAG}; uploading a fresh data bundle."
fi

"$ROOT_DIR/scripts/build_data_bundle.sh"
DATA_TARBALL="$ROOT_DIR/dist/symclatron_db.tar.gz"
if [[ ! -f "$DATA_TARBALL" ]]; then
  echo "Error: expected data bundle not found: $DATA_TARBALL" >&2
  exit 1
fi

gh release upload "$TAG" "$DATA_TARBALL" "$MANIFEST_PATH" --repo "$GITHUB_REPO" --clobber

echo "[OK] Uploaded: $(realpath "$DATA_TARBALL")"
echo "[OK] Uploaded: $(realpath "$MANIFEST_PATH")"
echo "Download URL: https://github.com/${GITHUB_REPO}/releases/download/${TAG}/$(basename "$DATA_TARBALL")"
