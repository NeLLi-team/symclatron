# symclatron: symbiont classifier

**ML-based classification of microbial symbiotic lifestyles**

symclatron is a tool that classifies microbial genomes (input is protein FASTA files (`.faa`)) into three symbiotic lifestyle categories:

- **Free-living**
- **Symbiont; Host-associated**
- **Symbiont; Obligate-intracellular**

## Installation and quick start

### Step 1: Install `pixi` (Requirement ⚠️)

```sh
curl -fsSL https://pixi.sh/install.sh | sh
```

More information about `pixi` can be found in the [pixi documentation](https://pixi.sh/).

### Step 2: Install `symclatron`

```sh
pixi global install -c conda-forge -c bioconda -c https://repo.prefix.dev/astrogenomics symclatron
symclatron setup
```

### Test the installation

```sh
symclatron test
```

## Setup data (required)

Before using `symclatron` for the first time, you need to download the required database files. This only needs to be done once.

```bash
symclatron setup
```

## Input file requirements

- **Input file format**: Protein FASTA files (`.faa`)
- **Quality**: Complete or near-complete genomes recommended, but good performance for MQ MAGs are expected

### Classify your genomes

```bash
symclatron classify --genome-dir /path/to/genomes/ --output-dir results/
```

### Getting help

```bash
symclatron --help

# Command-specific help
symclatron classify --help
symclatron setup --help

# Show version and information
symclatron --version
```

### Classification command

The main classification command with all options:

```bash
symclatron classify [OPTIONS]
```

**Options:**

- `--genome-dir, -i`: Directory containing genome FASTA files (.faa) [default: input_genomes]
- `--output-dir, -o`: Output directory for results [default: output_symclatron]
- `--keep-tmp`: Keep temporary files for debugging
- `--threads, -t`: Number of threads for HMMER searches [default: 2]
- `--quiet, -q`: Suppress progress messages
- `--verbose`: Show detailed progress information

**Examples:**

```bash
# Basic usage
symclatron classify --genome-dir genomes/ --output-dir results/

# With more threads and keeping temporary files
symclatron classify -i genomes/ -o results/ --threads 8 --keep-tmp

# Quiet mode
symclatron classify --genome-dir genomes/ --quiet

# Verbose mode with detailed progress
symclatron classify --genome-dir genomes/ --verbose
```

## Results

The classification results are saved in the specified output directory:

### Main output files

1. **`symclatron_results.tsv`** - Main classification results with columns:
   - `taxon_oid` - Genome identifier
   - `completeness_UNI56` - Completeness metric based on universal marker genes
   - `confidence` - Overall confidence score for the classification
   - `classification` - Final classification label:
     - `Free-living`
     - `Symbiont;Host-associated`
     - `Symbiont;Obligate-intracellular`

2. **`classification_summary.txt`** - Summary report with statistics

3. **Log files** - Detailed execution logs with timestamps

### Debug files

When using `--keep-tmp`, intermediate files are preserved in `tmp/` directory for analysis.

## Performance

symclatron is designed for efficiency:

- **>2 minutes per genome** on consumer-level laptops
- **Most recent benchmark**: 306 genomes in ~162 minutes (1.9 min/genome)
- **Memory efficient** - suitable for standard workstations

## Container usage

### Apptainer/Singularity

Pull the latest container:

```bash
apptainer pull docker://docker.io/jvillada/symclatron:latest
```

## Citation

If you use symclatron in your research, please cite:

A genomic catalog of Earth’s bacterial and archaeal symbionts.
Juan C. Villada, Yumary M. Vasquez, Gitta Szabo, Ewan Whittaker-Walker, Miguel F. Romero, Sarina Qin, Neha Varghese, Emiley A. Eloe-Fadrosh, Nikos C. Kyrpides, SymGs data consortium, Axel Visel, Tanja Woyke, Frederik Schulz
bioRxiv 2025.05.29.656868; doi: https://doi.org/10.1101/2025.05.29.656868

## Support

- **Repository**: [https://github.com/NeLLi-team/symclatron](https://github.com/NeLLi-team/symclatron)
- **Issues**: [https://github.com/NeLLi-team/symclatron/issues](https://github.com/NeLLi-team/symclatron/issues)
- **Author**: Juan C. Villada <jvillada@lbl.gov>