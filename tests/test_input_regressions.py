import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from symclatron import symclatron as sym


class InputPreprocessingTests(unittest.TestCase):
    def prepare_proteins(self, originals, directory="inputs"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        inputs = Path(temp.name) / directory
        inputs.mkdir(parents=True)
        for name, content in originals.items():
            (inputs / name).write_text(content)
        output = inputs / "results"
        tmp = output / "tmp"
        tmp.mkdir(parents=True)
        with patch.object(sym, "tmp_dir_path", str(tmp), create=True), patch.object(
            sym, "genomedir", str(inputs), create=True
        ):
            sym.validate_input(str(inputs), logging.getLogger(__name__), input_kind="proteins")
            prepared = sym.copy_genomes_to_tmp_dir(input_kind="proteins")
            sym.rename_genomes(prepared)
            sym.rename_all_proteins_in_fasta_files(prepared, str(output))
            sym.merge_genomes(prepared)
            sym.save_list_of_genomes(prepared)
        for name, content in originals.items():
            self.assertEqual((inputs / name).read_text(), content)
        return tmp, Path(prepared)

    def test_existing_internal_genome_names_do_not_overwrite_other_genomes(self):
        originals = {
            "alpha.faa": ">alpha_protein\nMPEPTIDE\n",
            "genome_1.faa": ">first_protein\nMELT\n",
            "genome_2.faa": ">second_protein\nMELK\n",
            "genome_10.faa": ">tenth_protein\nMPEEK\n",
        }
        tmp, prepared = self.prepare_proteins(originals)
        mapping = json.loads((tmp / "genomes_dict.json").read_text())
        self.assertEqual(mapping, {
            "genome_1": "alpha",
            "genome_2": "genome_1",
            "genome_3": "genome_10",
            "genome_4": "genome_2",
        })
        self.assertEqual(set((tmp / "genomes.list").read_text().splitlines()), set(mapping))
        merged_records = dict(sym._parse_fasta(tmp / "merged_genomes.faa"))
        self.assertEqual(len(merged_records), len(originals))
        for genome_id, original_id in mapping.items():
            original_header, original_sequence = originals[f"{original_id}.faa"].splitlines()
            self.assertEqual(merged_records[f"{genome_id}|protein_1"], original_sequence)
            proteins = json.loads((prepared / f"{genome_id}_dict.json").read_text())
            self.assertEqual(proteins, {"protein_1": original_header[1:]})

    def test_glob_characters_in_parent_directories_are_literal(self):
        tmp, prepared = self.prepare_proteins(
            {"alpha.faa": ">alpha_protein\nMPEPTIDE\n"},
            directory="batch[1]/bins?*[set]",
        )
        self.assertEqual(
            json.loads((tmp / "genomes_dict.json").read_text()), {"genome_1": "alpha"}
        )
        self.assertTrue((prepared / "genome_1_dict.json").is_file())
        self.assertEqual((tmp / "genomes.list").read_text(), "genome_1\n")
        self.assertEqual(
            list(sym._parse_fasta(tmp / "merged_genomes.faa")),
            [("genome_1|protein_1", "MPEPTIDE")],
        )

    def test_merging_fasta_without_terminal_newline_preserves_records(self):
        tmp, _ = self.prepare_proteins({
            "alpha.faa": ">alpha_protein\nMPEPTIDE",
            "beta.faa": ">beta_protein\nMELT",
        })
        self.assertEqual(
            list(sym._parse_fasta(tmp / "merged_genomes.faa")),
            [("genome_1|protein_1", "MPEPTIDE"), ("genome_2|protein_1", "MELT")],
        )

    def test_explicit_protein_kind_resolves_ambiguous_sequence_alphabet(self):
        tmp, _ = self.prepare_proteins({"alpha.faa": ">short_peptide\nMKKKKK\n"})
        original = tmp.parent.parent / "alpha.faa"
        self.assertEqual(sym._detect_sequence_type(original), "nucleotide")
        self.assertEqual(sym._detect_sequence_type(original, "proteins"), "protein")
        self.assertEqual(
            list(sym._parse_fasta(tmp / "merged_genomes.faa")),
            [("genome_1|protein_1", "MKKKKK")],
        )

    def test_explicit_protein_kind_still_rejects_nucleotide_only_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            fasta = Path(root) / "rna.fna"
            fasta.write_text(">rna\nACGUACGU\n")
            self.assertEqual(sym._detect_sequence_type(fasta, "proteins"), "nucleotide")
            with self.assertLogs(__name__, level="ERROR"), patch.object(sym.typer, "secho"):
                with self.assertRaises(sym.typer.Exit):
                    sym.validate_input(str(fasta), logging.getLogger(__name__), input_kind="proteins")


if __name__ == "__main__":
    unittest.main()
