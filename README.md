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

Create `conda` environment and install requirements:

```{bash}
mamba create -c conda-forge -c bioconda --name symclatron --file requirements.txt
```

### 💽  Setup data (run only once)

**Run inside the `symclatron/` folder:**

```{shell}
mamba activate symclatron
```

```{shell}
./symclatron setup
```

_______

## 🚀 Example run

```{shell}
mamba activate symclatron
```

```{shell}
cd symclatron/
```

### 👷🏻‍♀️  Run the classifier

**Run inside the `symclatron/` folder:**

### To get help

```{bash}
./symclatron classify --help

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

```{shell}
./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron
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

```bash
./symclatron classify --genome-dir data/test_genomes/ --save-dir test_output_symclatron --no-deltmp
```

This will preserve all intermediate files in the `tmp/` directory within your output directory.