# Changelog

## 0.10.12 — 2026-09-21

### Added

- Add `extra_results/feature_hits.tsv` to link classifier HMM features to original genome and protein identifiers, full-sequence scores and E-values. The report retains every protein tied for the highest recorded score and remains available after temporary-file cleanup.
- Add `protein_record_index` to classifier feature and UNI56 hit reports so distinct protein records with duplicate FASTA identifiers remain distinguishable.
- Add regression tests for input handling, protein and genome identifiers, feature reports, weighted distances, and database setup.

### Fixed

- Prevent genome files from overwriting one another during internal renaming when their names already resemble `genome_1.faa`.
- Handle literal brackets and wildcard characters in directory names, and preserve parent directory names when creating HMM result files.
- Keep FASTA records separate when input files lack a final newline.
- Honor `--input-kind proteins` when sequence letters are ambiguous between proteins and nucleotides.
- Preserve original genome identifiers in permanent bitscore and SHAP reports.
- Preserve original CDS identifiers during translation and predicted gene-number suffixes when contig headers contain descriptions.
- Align weighted-distance features with the training data's column order.
- Reject input paths that would be removed during temporary-workspace cleanup, including input symlinks.
- Preserve the existing database when replacement download, checksum verification, extraction, or installation fails. Retain a recoverable backup if restoration fails.
- Reject database archives without a nonempty supported data directory, and prevent archive links from writing outside the extraction directory.

### Documentation

- Explain how to connect feature and UNI56 reports to the corresponding protein records, including tied scores, repeated domains, and duplicate identifiers.
- Clarify that SHAP reports explain the `symreg` score, and that permissive classifier HMM hits alone do not establish protein function.
- Document database replacement behavior with `setup --force`.
