# symclatron: symbiont classifier

## 💾 Installation

Clone the `symclatron` repository:

```{shell}
git clone https://github.com/juanvillada/symclatron.git
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

2. The repository includes a `pixi.toml` file with all necessary dependencies. To create the environment, run:

```{bash}
pixi install
```

3. To run symclatron commands with pixi:

```{bash}
pixi run -- ./symclatron setup
pixi run -- ./symclatron classify --help
```

### 💽  Setup data (run only once)

**Run inside the `symclatron/` folder:**

With conda/mamba:
```{shell}
mamba activate symclatron
./symclatron setup
```

With pixi:
```{shell}
pixi run -- ./symclatron setup
```

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
pixi run -- ./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron
```

### 🕺🏻 Results

The classification results are saved in the specified output directory. The main output files are:

1. `symclatron_results.tsv` - Contains the final classification results with the following columns:
   - `taxon_oid` - Genome identifier
   - `completeness_UNI56` - Completeness metric based on universal marker genes
   - `confidence` - Overall confidence score for the classification
   - `classification` - Final classification label (Free-living, Symbiont;Host-associated, or Symbiont;Obligate-intracellular)

### 🐳 symclatron container

#### Apptainer

⚠️⚠️⚠️ Note: The paths to the input genomes and output directory must be absolute. ⚠️⚠️⚠️

```bash
apptainer pull \
        docker://docker.io/jvillada/symclatron:latest

ABSOLUTE_PATH_TO_DIR_WITH_FAA_FILES=""
ABSOLUTE_PATH_TO_OUTPUT_DIR="" # this directory must not exist! symclatron will create it.

apptainer run \
        --pwd /usr/src/symclatron \
        docker://docker.io/jvillada/symclatron:latest \
        symclatron \
        classify \
        --genome-dir ${ABSOLUTE_PATH_TO_DIR_WITH_FAA_FILES} \
        --save-dir ${ABSOLUTE_PATH_TO_OUTPUT_DIR}
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
pixi run -- ./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron --no-deltmp
```

This will preserve all intermediate files in the `tmp/` directory within your output directory.