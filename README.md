# symclatron: symbiont classifier

## 💾 Installation

Clone the `symclatron` repository:

```{shell}
git clone https://github.com/NeLLi-team/symclatron.git
```

```{bash}
cd symclatron/
chmod u+x symclatron
```

### Option 1: Using Conda/Mamba

Create `conda` environment and install requirements:

```{bash}
mamba create -c conda-forge -c bioconda --name symclatron --file requirements.txt
```

### Option 2: Using Pixi

[Pixi](https://pixi.sh/) is a fast, multi-platform package manager that can be used as an alternative to conda/mamba.

1. Install Pixi by following the instructions at [https://pixi.sh/](https://pixi.sh/)

2. If you have any active virtual environments (like conda, venv, etc.), deactivate them first:

```{bash}
# For conda/mamba environments
conda deactivate

# For venv environments
deactivate
```

3. The repository includes a `pixi.toml` file with all necessary dependencies. To create the environment, run:

```{bash}
pixi install
```

4. To run symclatron commands with pixi:

```{bash}
# Run the setup command
pixi run -- ./symclatron setup

# Get help for the classify command
pixi run -- ./symclatron classify --help
```

5. Alternatively, you can use the predefined pixi tasks:

```{bash}
# Run the setup command
pixi run setup

# Run the classify command (default options)
pixi run classify

# Run the classify command with test genomes
pixi run classify-test

# Run the classify command with test genomes, keeping temporary files
pixi run classify-test-keep-tmp

# For custom options, use the direct command
pixi run -- ./symclatron classify --genome-dir data/test_genomes/ --save-dir custom_output_dir
```

### 💽  Setup data (run only once)

**Run inside the `symclatron/` folder:**

#### Option 1: Using the setup command

With conda/mamba:
```{shell}
mamba activate symclatron
./symclatron setup
```

With pixi:
```{shell}
pixi run -- ./symclatron setup
```

#### Option 2: Manual extraction

If the setup command fails, you can manually extract the data.tar.gz file:

```{shell}
tar -xzf data.tar.gz
```

This will create a `data` directory with all the necessary files, including test genomes in the `data/test_genomes/` directory.

_______

## 🚀 Example run

### Option 1: Using Conda/Mamba

```{shell}
mamba activate symclatron
```

```{shell}
cd symclatron/
```

### Option 2: Using Pixi

No activation is needed with pixi. Just make sure you're in the symclatron directory:

```{shell}
cd symclatron/
```

### 👷🏻‍♀️  Run the classifier

**Run inside the `symclatron/` folder:**

### To get help

With conda/mamba:
```{bash}
./symclatron classify --help
```

With pixi:
```{bash}
pixi run -- ./symclatron classify --help
```

Output:
```
# Usage: symclatron classify [OPTIONS]
#
# ╭─ Options ───────────────────────────────────────────────────────────────────────────────────╮
# │ --genome-dir                   TEXT  [default: input_genomes]                               │
# │ --save-dir                     TEXT  [default: output_symclatron]                           │
# │ --deltmp        --no-deltmp          [default: deltmp]                                      │
# │ --help                               Show this message and exit.                            │
# ╰─────────────────────────────────────────────────────────────────────────────────────────────╯
```

**Run inside the `symclatron/` folder:**

With conda/mamba:
```{shell}
./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron
```

With pixi:
```{shell}
# Using the direct command
pixi run -- ./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron

# Or using the predefined task with test genomes
pixi run classify-test

# Or using the predefined task with test genomes, keeping temporary files
pixi run classify-test-keep-tmp

# For custom options, use the direct command
pixi run -- ./symclatron classify --genome-dir data/test_genomes/ --save-dir custom_output_dir
```

**Running from a different directory:**

With conda/mamba:
```{shell}
/path/to/symclatron/symclatron classify --genome-dir /path/to/genome/files/ --save-dir /path/to/output/directory
```

### 🕺🏻 Results

The classification results are saved in the specified output directory. The main output files are:

1. `symclatron_results.tsv` - Contains the final classification results with the following columns:
   - `taxon_oid` - Genome identifier
   - `completeness_UNI56` - Completeness metric based on universal marker genes
   - `confidence` - Overall confidence score for the classification
   - `classification` - Final classification label (Free-living, Symbiont;Host-associated, or Symbiont;Obligate-intracellular)

2. `classification_summary.txt` - A summary report of the classification results with statistics

### 🐳 symclatron container

#### Docker/Podman

```bash
# Pull the image
docker pull docker.io/jvillada/symclatron:latest
# or with Podman
podman pull docker.io/jvillada/symclatron:latest

# Run the container
docker run --rm -v /path/to/input/genomes:/input -v /path/to/output/dir:/output \
    docker.io/jvillada/symclatron:latest \
    pixi run -- ./symclatron classify --genome-dir /input --save-dir /output

# or with Podman
podman run --rm -v /path/to/input/genomes:/input -v /path/to/output/dir:/output \
    docker.io/jvillada/symclatron:latest \
    pixi run -- ./symclatron classify --genome-dir /input --save-dir /output
```

#### Apptainer/Singularity

```bash
# Pull the image
apptainer pull docker://docker.io/jvillada/symclatron:latest

# Run the container
# Note: Make sure to specify --pwd to work in the correct directory
apptainer run \
    --pwd /usr/src/symclatron \
    -B /path/to/input/genomes:/input \
    -B /path/to/output/dir:/output \
    symclatron_latest.sif \
    pixi run -- ./symclatron classify --genome-dir /input --save-dir /output

# Or if you want to use the predefined tasks
apptainer run \
    --pwd /usr/src/symclatron \
    -B /path/to/test/output/dir:/output \
    symclatron_latest.sif \
    pixi run classify --save-dir /output

# For running directly without pulling first
apptainer run \
    --pwd /usr/src/symclatron \
    -B /path/to/input/genomes:/input \
    -B /path/to/output/dir:/output \
    docker://docker.io/jvillada/symclatron:latest \
    pixi run -- ./symclatron classify --genome-dir /input --save-dir /output
```

## 🛠️ Advanced Options

### Preserving Temporary Files

By default, the temporary files created during the classification process are deleted after the analysis is complete. To keep these files (useful for debugging or advanced analysis), use the `--no-deltmp` flag:

With conda/mamba:
```bash
./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron --no-deltmp
```

With pixi:
```bash
# Using the direct command
pixi run -- ./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron --no-deltmp

# Or using the predefined task with test genomes, keeping temporary files
pixi run classify-test-keep-tmp

# For custom options, use the direct command
pixi run -- ./symclatron classify --genome-dir data/test_genomes/ --save-dir custom_output_dir --no-deltmp
```

This will preserve all intermediate files in the `tmp/` directory within your output directory.
