#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITHUB_REPO="${GITHUB_REPO:-NeLLi-team/symclatron}"

TAG_OR_VERSION="${1:-}"
if [[ -z "$TAG_OR_VERSION" ]]; then
  echo "Usage: $(basename "$0") <tag|version>" >&2
  echo "Example: $(basename "$0") 0.8.0   # uploads to tag v0.8.0" >&2
  exit 1
fi

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

"$ROOT_DIR/scripts/build_data_bundle.sh"
DATA_TARBALL="$ROOT_DIR/dist/symclatron_db.tar.gz"
if [[ ! -f "$DATA_TARBALL" ]]; then
  echo "Error: expected data bundle not found: $DATA_TARBALL" >&2
  exit 1
fi

if ! gh release view "$TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
  echo "GitHub release not found for ${TAG}; creating it."
  gh release create "$TAG" --repo "$GITHUB_REPO" --title "$TAG" --generate-notes
fi

gh release upload "$TAG" "$DATA_TARBALL" --repo "$GITHUB_REPO" --clobber

echo "[OK] Uploaded: $(realpath "$DATA_TARBALL")"
echo "Download URL: https://github.com/${GITHUB_REPO}/releases/download/${TAG}/$(basename "$DATA_TARBALL")"
echo "Latest URL:   https://github.com/${GITHUB_REPO}/releases/latest/download/$(basename "$DATA_TARBALL")"
