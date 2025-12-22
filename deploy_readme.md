# Release guide (symclatron)

This doc summarizes the release flow for PyPI + prefix.dev (pixi) and the GitHub push/tag steps.

## Requirements

- `flit` and `twine` available in the Python environment used by `pixi run`
- `rattler-build` available on PATH
- Environment variables:
  - `PYPI_API_TOKEN`
  - `PREFIX_API_KEY`

## Preflight (clean git working tree)

`flit build` fails when there are untracked or deleted files. Before running the deploy script, make sure the working tree is clean by committing, stashing, or ignoring local changes.

```bash
git status --porcelain

# If output is not empty, either commit your changes:
git add -A
git commit -m "Prep for release"

# Or stash them (including untracked files):
git stash -u
```

## Standard release (recommended)

```bash
VERSION="0.8.0"
pixi run ./scripts/deploy.sh "$VERSION" --push --tag
```

What it does:
- Updates `__version__` in `symclatron/__init__.py` and `symclatron/symclatron.py`
- Updates `context.version` and `sha256` in `recipe.yaml`
- Builds sdist/wheel and uploads to PyPI
- Builds conda package and uploads to prefix.dev channel `astrogenomics`
- Commits release changes, tags `v<version>`, and pushes to GitHub

## If you already ran deploy without pushing

```bash
VERSION="<version>"
git add .
git commit -m "Release $VERSION"
git push origin main
git tag "v$VERSION"
git push origin "v$VERSION"
```

## Notes

- `flit build` fails if there are untracked files in the repo; either add them, ignore them, or stash them before running the deploy script.
- PyPI propagation can take a few minutes. The deploy script waits by default; adjust with:
  - `PYPI_WAIT_TIMEOUT` (seconds, default 600, set to 0 to skip)
  - `PYPI_WAIT_INTERVAL` (seconds, default 10)

## Docker image

The image installs symclatron from the `astrogenomics` prefix.dev channel, runs `symclatron setup` during build, and exposes `symclatron` as the entrypoint.

### Build and push (multi-arch)

```bash
VERSION="0.7.2"
scripts/docker_publish.sh "$VERSION"
```

Optional overrides:
- `DOCKER_REPO` (default: `astrogenomics/symclatron`)
- `PLATFORMS` (default: `linux/amd64,linux/arm64`)

### Run (Docker Desktop / Linux)

```bash
docker run --rm -it astrogenomics/symclatron:"$VERSION" --help

docker run --rm -it \
  -v "$PWD:/work" -w /work \
  astrogenomics/symclatron:"$VERSION" classify --genome-dir genomes --output-dir results
```

### Run on HPC (Apptainer/Singularity)

```bash
apptainer pull symclatron_${VERSION}.sif docker://astrogenomics/symclatron:${VERSION}
apptainer exec symclatron_${VERSION}.sif symclatron --help

apptainer exec --bind "$PWD:/work" symclatron_${VERSION}.sif \
  symclatron classify --genome-dir /work/genomes --output-dir /work/results
```

### Notes

- The image already includes the data from `symclatron setup`. Re-running `symclatron setup` inside the container is optional.
- Docker Desktop must be set to Linux containers (default) on macOS/Windows.
