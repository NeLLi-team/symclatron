# symclatron: symbiont classifier

![Figure 1](assets/fig_1_main.png)

**ML-based classification of microbial symbiotic lifestyles**

symclatron is a tool that classifies microbial genomes (protein FASTA, or nucleotide FASTA with automatic protein prediction) into three lifestyle categories:

- **Free-living**
- **Symbiont; Host-associated**
- **Symbiont; Obligate-intracellular**

## Installation and quick start

Recommended install paths are `Pixi` (recommended) or `Mamba`/`Conda`.

Validated packaged installs currently include `Linux x86_64` and Apple Silicon `arm64` macOS for the `pixi global install` workflow.

### Option 1: `Pixi` (recommended)

Install `pixi`:

```sh
curl -fsSL https://pixi.sh/install.sh | sh
```

More information about `pixi` can be found in the [pixi documentation](https://pixi.sh/).

Install, setup, and test:

```sh
pixi global install -c conda-forge -c bioconda -c https://repo.prefix.dev/astrogenomics symclatron
symclatron setup --force
symclatron test
# Outputs are written under `output_test_Symclatron_<DATETIME>/faa` and `output_test_Symclatron_<DATETIME>/fna`
# (or under `--output-dir` if provided).
```

### Option 2: Mamba or Conda

```sh
mamba create -n symclatron-0.9.10 -c conda-forge -c bioconda -c https://repo.prefix.dev/astrogenomics symclatron
mamba run -n symclatron-0.9.10 symclatron setup
mamba run -n symclatron-0.9.10 symclatron test
# Outputs are written under `output_test_Symclatron_<DATETIME>/faa` and `output_test_Symclatron_<DATETIME>/fna`
# (or under `--output-dir` if provided).
```

Note: `symcla` is a short alias for `symclatron`. Any command works with either name (for example, `symcla test`).

## Setup data (required)

Before using `symclatron` for the first time, you need to download the required database files. This only needs to be done once.

```bash
symclatron setup
```

## Input file requirements

- **Input**: `--genome-dir` points to a directory with one genome FASTA per file, or to a single FASTA file
- **Supported FASTA types**:
  - **Proteins (recommended)**: `.faa` (also accepts common protein FASTA suffixes, optionally gzipped)
  - **Nucleotide contigs/assemblies**: `.fa`, `.fna`, `.fasta` (proteins predicted with `pyrodigal`)
  - **Nucleotide genes/CDS**: `.ffn`, `.fnn` (translated in-frame)
- **Quality**: Complete or near-complete genomes recommended, but good performance for MQ MAGs are expected

`symclatron` auto-detects whether each input file contains proteins, genes, or contigs and converts nucleotide inputs to proteins before running the standard workflow.
If your nucleotide file extensions are ambiguous, you can override detection with `--input-kind contigs` or `--input-kind genes`.

### Classify your genomes

```bash
# Protein FASTA input
symclatron classify --genome-dir /path/to/genomes/ --output-dir results/

# Nucleotide contigs/assemblies input (auto protein prediction)
symclatron classify --genome-dir /path/to/contigs/ --output-dir results/

# Ambiguous nucleotide files: force contig mode and only use .fna files
symclatron classify --genome-dir /path/to/inputs/ --input-kind contigs --input-ext .fna --output-dir results/

# Apply a conservative confidence threshold and relabel lower-confidence calls as Unknown
symclatron classify --genome-dir /path/to/genomes/ --confidence-threshold 0.725 --output-dir results/
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

- `--genome-dir, -i`: Directory (or FASTA file) containing genome inputs (.faa/.fa/.fna/.fasta/.ffn/.fnn) [default: input_genomes]
- `--input-kind`: Force input kind: `auto`, `proteins`, `genes`, `contigs` [default: auto]
- `--input-ext`: Only include files with these extensions (repeatable), e.g. `--input-ext .fna` (also matches `.fna.gz`)
- `--output-dir, -o`: Output directory for results [default: output_Symclatron_<DATETIME>]
- `--keep-tmp`: Keep temporary files for debugging
- `--threads, -t`: Number of threads for HMMER searches [default: 2]
- `--confidence-threshold`: Optional confidence threshold for conservative interpretation; when provided, low-confidence predictions are relabeled as `Unknown` in an additional `classification_thresholded` column
- `--quiet, -q`: Suppress progress messages
- `--verbose`: Show detailed progress information

**Examples:**

```bash
# Basic usage
symclatron classify --genome-dir genomes/ --output-dir results/

# With more threads and keeping temporary files
symclatron classify -i genomes/ -o results/ --threads 8 --keep-tmp

# Apply the recommended confidence threshold for conservative interpretation
symclatron classify --genome-dir genomes/ --confidence-threshold 0.725

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
   - `classification` - Raw classification label:
     - `Free-living`
     - `Symbiont;Host-associated`
     - `Symbiont;Obligate-intracellular`
   - `classification_thresholded` - Optional thresholded label when `--confidence-threshold` is used; lower-confidence predictions are reported as `Unknown`
   - `passes_confidence_threshold` - Optional boolean flag indicating whether the prediction passed the chosen threshold

2. **`classification_summary.txt`** - Summary report with statistics

3. **Log files** - Detailed execution logs with timestamps

### Debug files

When using `--keep-tmp`, intermediate files are preserved in `tmp/` directory for analysis.

### Confidence guidance

The raw `classification` column always reports the highest-probability class from the model. For conservative interpretation, we recommend using a confidence threshold of `0.725`. When `--confidence-threshold 0.725` is supplied, the results table also includes `classification_thresholded` and `passes_confidence_threshold` columns so that lower-confidence predictions are explicitly separated from higher-confidence calls.

## Performance

symclatron is designed for efficiency:

- **>2 minutes per genome** on consumer-level laptops
- **Most recent benchmark**: 306 genomes in ~162 minutes (1.9 min/genome)
- **Memory efficient** - suitable for standard workstations

## Citation

If you use symclatron in your research, please cite:

A genomic catalog of Earth’s bacterial and archaeal symbionts.
Juan C. Villada, Yumary M. Vasquez, Gitta Szabo, Ewan Whittaker-Walker, Miguel F. Romero, Sarina Qin, Neha Varghese, Emiley A. Eloe-Fadrosh, Nikos C. Kyrpides, SymGs data consortium, Axel Visel, Tanja Woyke, Frederik Schulz
bioRxiv 2025.05.29.656868; doi: https://doi.org/10.1101/2025.05.29.656868

## Support

- **Repository**: [https://github.com/NeLLi-team/symclatron](https://github.com/NeLLi-team/symclatron)
- **Issues**: [https://github.com/NeLLi-team/symclatron/issues](https://github.com/NeLLi-team/symclatron/issues)
- **Author**: Juan C. Villada <jvillada@lbl.gov>
