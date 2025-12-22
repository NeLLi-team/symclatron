#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=""
DO_GIT_PUSH=0
DO_GIT_TAG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      DO_GIT_PUSH=1
      shift
      ;;
    --tag)
      DO_GIT_TAG=1
      shift
      ;;
    -*)
      echo "Unknown option: $1"
      exit 1
      ;;
    *)
      if [[ -z "$VERSION" ]]; then
        VERSION="$1"
        shift
      else
        echo "Unexpected argument: $1"
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "Usage: $(basename "$0") <version> [--push] [--tag]"
  exit 1
fi

: "${PYPI_API_TOKEN:?PYPI_API_TOKEN must be set in the environment}"
: "${PREFIX_API_KEY:?PREFIX_API_KEY must be set in the environment}"

if ! python -m flit --version >/dev/null 2>&1; then
  echo "flit is required. Install with: python -m pip install flit"
  exit 1
fi

if ! python -m twine --version >/dev/null 2>&1; then
  echo "twine is required. Install with: python -m pip install twine"
  exit 1
fi

if ! command -v rattler-build >/dev/null 2>&1; then
  echo "rattler-build is required. Install with: pixi global install rattler-build"
  exit 1
fi

python - <<'PY' "$VERSION" "$ROOT_DIR"
import pathlib
import re
import sys

version = sys.argv[1]
root = pathlib.Path(sys.argv[2])

version_files = [
    root / "symclatron/__init__.py",
    root / "symclatron/symclatron.py",
]

for path in version_files:
    text = path.read_text()
    new_text, count = re.subn(
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"Expected one __version__ assignment in {path}")
    path.write_text(new_text)

recipe = root / "recipe.yaml"
lines = recipe.read_text().splitlines()
for i, line in enumerate(lines):
    if line.strip() == "context:":
        if i + 1 < len(lines) and lines[i + 1].lstrip().startswith("version:"):
            lines[i + 1] = f"  version: {version}"
            break
else:
    raise SystemExit("Could not find context.version in recipe.yaml")

recipe.write_text("\n".join(lines) + "\n")
PY

(
  cd "$ROOT_DIR"
  python -m flit build
)

SDIST="$ROOT_DIR/dist/symclatron-${VERSION}.tar.gz"
if [[ ! -f "$SDIST" ]]; then
  echo "Expected sdist not found: $SDIST"
  exit 1
fi

SHA256="$(python - <<'PY' "$SDIST"
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
hasher = hashlib.sha256()
with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        hasher.update(chunk)
print(hasher.hexdigest())
PY
)"

python - <<'PY' "$SHA256" "$ROOT_DIR"
import pathlib
import sys

sha = sys.argv[1]
root = pathlib.Path(sys.argv[2])
recipe = root / "recipe.yaml"
lines = recipe.read_text().splitlines()
for i, line in enumerate(lines):
    if line.lstrip().startswith("sha256:"):
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = f"{indent}sha256: {sha}"
        break
else:
    raise SystemExit("Could not find sha256 in recipe.yaml")

recipe.write_text("\n".join(lines) + "\n")
PY

(
  cd "$ROOT_DIR"
  TWINE_USERNAME="__token__" TWINE_PASSWORD="$PYPI_API_TOKEN" \
    python -m twine upload --skip-existing "dist/symclatron-${VERSION}"*
)

PYPI_WAIT_TIMEOUT="${PYPI_WAIT_TIMEOUT:-600}"
PYPI_WAIT_INTERVAL="${PYPI_WAIT_INTERVAL:-10}"
PYPI_SDIST_URL="https://pypi.org/packages/source/s/symclatron/symclatron-${VERSION}.tar.gz"

python - <<'PY' "$PYPI_SDIST_URL" "$PYPI_WAIT_TIMEOUT" "$PYPI_WAIT_INTERVAL"
import sys
import time
import urllib.error
import urllib.request

url = sys.argv[1]
timeout_s = int(sys.argv[2])
interval_s = int(sys.argv[3])

if timeout_s <= 0:
    raise SystemExit(0)

deadline = time.time() + timeout_s
while True:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as resp:
            if 200 <= resp.status < 400:
                print(f"[OK] PyPI sdist available: {url}")
                break
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            print(f"PyPI check failed with HTTP {exc.code}; retrying...")
    except Exception as exc:
        print(f"PyPI check failed: {exc}; retrying...")

    if time.time() >= deadline:
        raise SystemExit(f"Timed out waiting for PyPI sdist: {url}")
    time.sleep(interval_s)
PY

BUILD_DIR="$ROOT_DIR/dist/conda"
mkdir -p "$BUILD_DIR"

rattler-build build -r "$ROOT_DIR/recipe.yaml" -c conda-forge -c bioconda --output-dir "$BUILD_DIR"

mapfile -t PKGS < <(find "$BUILD_DIR" -type f \( -name "*.conda" -o -name "*.tar.bz2" \))
if [[ ${#PKGS[@]} -eq 0 ]]; then
  echo "No build artifacts found in $BUILD_DIR"
  exit 1
fi

rattler-build upload prefix --channel astrogenomics --api-key "$PREFIX_API_KEY" --skip-existing "${PKGS[@]}"

if [[ "$DO_GIT_PUSH" -eq 1 ]]; then
  (
    cd "$ROOT_DIR"
    git add symclatron/__init__.py symclatron/symclatron.py recipe.yaml scripts/deploy.sh
    if git diff --cached --quiet; then
      echo "No release changes staged for git commit."
      exit 0
    fi
    git commit -m "Release ${VERSION}"
    if [[ "$DO_GIT_TAG" -eq 1 ]]; then
      git tag "v${VERSION}"
    fi
    git push origin HEAD
    if [[ "$DO_GIT_TAG" -eq 1 ]]; then
      git push origin "v${VERSION}"
    fi
  )
fi

echo "Release complete: ${VERSION}"
