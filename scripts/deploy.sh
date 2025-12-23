#!/usr/bin/env bash
set -euo pipefail
set -o errtrace

ts() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*"; }
step() { CURRENT_STEP="$*"; echo; log "==> ${CURRENT_STEP}"; }

CURRENT_STEP="initializing"
on_error() {
  local exit_code="$?"
  log "[ERROR] Step failed: ${CURRENT_STEP} (exit=${exit_code}, line=${BASH_LINENO[0]})"
  log "Tip: re-run after fixing the issue; deploy.sh stops on the first error."
  exit "$exit_code"
}
trap on_error ERR

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=""
DO_GIT_PUSH=0
DO_GIT_TAG=0
DO_DATA_BUNDLE=0

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
    --data-bundle|--data)
      DO_DATA_BUNDLE=1
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
  echo "Usage: $(basename "$0") <version> [--push] [--tag] [--data-bundle]"
  exit 1
fi

step "Configuration"
log "ROOT_DIR: ${ROOT_DIR}"
log "VERSION: ${VERSION}"
log "Options: --push=${DO_GIT_PUSH} --tag=${DO_GIT_TAG} --data-bundle=${DO_DATA_BUNDLE}"

: "${PYPI_API_TOKEN:?PYPI_API_TOKEN must be set in the environment}"
: "${PREFIX_API_KEY:?PREFIX_API_KEY must be set in the environment}"

if [[ "$DO_DATA_BUNDLE" -eq 1 && ( "$DO_GIT_PUSH" -ne 1 || "$DO_GIT_TAG" -ne 1 ) ]]; then
  echo "--data-bundle requires --push and --tag (it uploads to the GitHub Release for the tag)."
  exit 1
fi

step "Preflight checks"
if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  log "Git repo detected: $(git -C "$ROOT_DIR" rev-parse --show-toplevel)"
  log "Git HEAD: $(git -C "$ROOT_DIR" rev-parse --short HEAD)"
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    echo "Git working tree is not clean. Commit, stash, or ignore changes before running $(basename "$0")."
    git -C "$ROOT_DIR" status --porcelain
    exit 1
  fi
  log "Git working tree: clean"
else
  log "Git not detected (continuing)"
fi

if ! python -m flit --version >/dev/null 2>&1; then
  echo "flit is required. Install with: python -m pip install flit"
  exit 1
fi
log "flit: $(python -m flit --version 2>/dev/null || true)"

if ! python -m twine --version >/dev/null 2>&1; then
  echo "twine is required. Install with: python -m pip install twine"
  exit 1
fi
log "twine: $(python -m twine --version 2>/dev/null || true)"

if ! command -v rattler-build >/dev/null 2>&1; then
  echo "rattler-build is required. Install with: pixi global install rattler-build"
  exit 1
fi
log "rattler-build: $(rattler-build --version 2>/dev/null || true)"

step "Update version strings"
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
    print(f"[deploy] Updated __version__ in: {path.resolve()}")

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
print(f"[deploy] Updated context.version in: {recipe.resolve()}")

readme = root / "README.md"
if readme.exists():
    readme_text = readme.read_text()
    readme_text, readme_count = re.subn(
        r"symclatron-\d+\.\d+\.\d+",
        f"symclatron-{version}",
        readme_text,
    )
    if readme_count == 0:
        raise SystemExit("Could not find symclatron-<version> in README.md")
    readme.write_text(readme_text)
    print(f"[deploy] Updated README version strings in: {readme.resolve()} ({readme_count} replacements)")
PY

step "Build sdist/wheel (flit)"
(
  cd "$ROOT_DIR"
  python -m flit build
)

SDIST="$ROOT_DIR/dist/symclatron-${VERSION}.tar.gz"
if [[ ! -f "$SDIST" ]]; then
  echo "Expected sdist not found: $SDIST"
  exit 1
fi
log "Built sdist: ${SDIST}"

step "Compute sdist sha256"
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
log "sdist sha256: ${SHA256}"

step "Update conda recipe sha256"
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
print(f"[deploy] Updated sha256 in: {recipe.resolve()}")
PY

step "Upload to PyPI (twine)"
log "Uploading: ${ROOT_DIR}/dist/symclatron-${VERSION}*"
(
  cd "$ROOT_DIR"
  TWINE_USERNAME="__token__" TWINE_PASSWORD="$PYPI_API_TOKEN" \
    python -m twine upload --skip-existing "dist/symclatron-${VERSION}"*
)

PYPI_WAIT_TIMEOUT="${PYPI_WAIT_TIMEOUT:-600}"
PYPI_WAIT_INTERVAL="${PYPI_WAIT_INTERVAL:-10}"
PYPI_SDIST_URL="https://pypi.org/packages/source/s/symclatron/symclatron-${VERSION}.tar.gz"

step "Wait for PyPI propagation"
log "PyPI check URL: ${PYPI_SDIST_URL}"
log "Timeout: ${PYPI_WAIT_TIMEOUT}s (interval ${PYPI_WAIT_INTERVAL}s)"
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

step "Build conda package (rattler-build)"
log "Recipe: ${ROOT_DIR}/recipe.yaml"
log "Output dir: ${BUILD_DIR}"
rattler-build build -r "$ROOT_DIR/recipe.yaml" -c conda-forge -c bioconda --output-dir "$BUILD_DIR"

mapfile -t PKGS < <(find "$BUILD_DIR" -type f \( -name "*.conda" -o -name "*.tar.bz2" \))
if [[ ${#PKGS[@]} -eq 0 ]]; then
  echo "No build artifacts found in $BUILD_DIR"
  exit 1
fi
log "Conda build artifacts:"
for pkg in "${PKGS[@]}"; do
  log "  - ${pkg}"
done

step "Upload conda package to prefix.dev"
log "Channel: astrogenomics"
rattler-build upload prefix --channel astrogenomics --api-key "$PREFIX_API_KEY" --skip-existing "${PKGS[@]}"

if [[ "$DO_GIT_PUSH" -eq 1 ]]; then
  step "Git commit/tag/push"
  (
    cd "$ROOT_DIR"
    log "Staging release files"
    git add symclatron/__init__.py symclatron/symclatron.py pyproject.toml recipe.yaml README.md scripts/deploy.sh
    if git diff --cached --quiet; then
      echo "No release changes staged for git commit."
      exit 0
    fi
    log "Committing release changes"
    git commit -m "Release ${VERSION}"
    if [[ "$DO_GIT_TAG" -eq 1 ]]; then
      TAG="v${VERSION}"
      log "Creating git tag: ${TAG}"
      git tag "$TAG"
    fi
    log "Pushing to origin"
    git push origin HEAD
    if [[ "$DO_GIT_TAG" -eq 1 ]]; then
      log "Pushing tag to origin: ${TAG}"
      git push origin "$TAG"
      if command -v gh >/dev/null 2>&1; then
        if gh auth status >/dev/null 2>&1; then
          log "Ensuring GitHub Release exists: ${TAG}"
          if gh release view "$TAG" >/dev/null 2>&1; then
            echo "GitHub release already exists: ${TAG}"
          else
            if ! gh release create "$TAG" --title "$TAG" --generate-notes; then
              echo "Warning: failed to create GitHub release for ${TAG}"
            fi
          fi

          if [[ "$DO_DATA_BUNDLE" -eq 1 ]]; then
            step "Build and upload data bundle to GitHub Release"
            if [[ ! -d "$ROOT_DIR/data" ]]; then
              echo "Error: data directory not found at: $ROOT_DIR/data"
              echo "Tip: run 'symclatron setup' first (or populate data/ before deploying)."
              exit 1
            fi
            log "Building data bundle from: ${ROOT_DIR}/data"
            "$ROOT_DIR/scripts/build_data_bundle.sh"
            DATA_TARBALL="$ROOT_DIR/dist/symclatron_db.tar.gz"
            if [[ ! -f "$DATA_TARBALL" ]]; then
              echo "Error: expected data bundle not found: $DATA_TARBALL"
              exit 1
            fi
            log "Uploading data bundle: ${DATA_TARBALL}"
            if ! gh release upload "$TAG" "$DATA_TARBALL" --clobber; then
              echo "Error: failed to upload data bundle to GitHub Release ${TAG}"
              exit 1
            fi
            log "Data bundle URL: https://github.com/NeLLi-team/symclatron/releases/download/${TAG}/$(basename "$DATA_TARBALL")"
            echo "[OK] Uploaded data bundle to GitHub Release: ${TAG}"
          fi
        else
          if [[ "$DO_DATA_BUNDLE" -eq 1 ]]; then
            echo "Error: gh is installed but not authenticated; run 'gh auth login' to upload the data bundle."
            exit 1
          fi
          echo "gh is installed but not authenticated; run 'gh auth login' to enable automatic GitHub Releases."
        fi
      else
        if [[ "$DO_DATA_BUNDLE" -eq 1 ]]; then
          echo "Error: gh CLI not found; install it to upload the data bundle."
          exit 1
        fi
        echo "gh CLI not found; create a GitHub Release for tag ${TAG} in the GitHub UI."
      fi
    fi
  )
fi

step "Done"
log "Release complete: ${VERSION}"
