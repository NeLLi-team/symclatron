import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from symclatron import symclatron as sym


class ProteinPathTests(unittest.TestCase):
    def test_prepare_proteins_in_directory_containing_faa(self):
        for directory in ("goodbins.faas", "parent.faa/good bins.faas", "ordinary"):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as root:
                inputs = Path(root) / directory
                inputs.mkdir(parents=True)
                originals = {
                    "alpha.faa": ">alpha_protein description\nMPEPTIDE\n",
                    "beta.faa.backup.faa": ">beta_protein\nMPEPTIDE\n>second\nMPEPTIDE\n",
                }
                for name, content in originals.items():
                    (inputs / name).write_text(content)
                output = inputs / "symclatron"
                tmp = output / "tmp"
                tmp.mkdir(parents=True)
                with patch.object(sym, "tmp_dir_path", str(tmp), create=True), patch.object(
                    sym, "genomedir", str(inputs), create=True
                ):
                    prepared = sym.copy_genomes_to_tmp_dir(input_kind="proteins", input_ext=["faa"])
                    sym.rename_genomes(prepared)
                    sym.rename_all_proteins_in_fasta_files(prepared, str(output))
                    sym.merge_genomes(prepared)
                    sym.save_list_of_genomes(prepared)

                renamed = Path(prepared)
                self.assertEqual(
                    json.loads((tmp / "genomes_dict.json").read_text()),
                    {"genome_1": "alpha", "genome_2": "beta.faa.backup"},
                )
                self.assertEqual(
                    json.loads((renamed / "genome_2_dict.json").read_text()),
                    {"protein_1": "beta_protein", "protein_2": "second"},
                )
                self.assertEqual(
                    (renamed / "genome_2.faa").read_text(),
                    ">genome_2|protein_1\nMPEPTIDE\n>genome_2|protein_2\nMPEPTIDE\n",
                )
                self.assertEqual((tmp / "merged_genomes.faa").read_text().count(">"), 3)
                self.assertFalse(list(renamed.glob("*_renamed.faa")))
                for name, content in originals.items():
                    self.assertEqual((inputs / name).read_text(), content)


class Uni56DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.tmp = root / "tmp"
        self.tmp.mkdir()
        self.extra = root / "extra_results"
        self.extra.mkdir()
        self.renamed = self.tmp / "renamed_genomes"
        self.renamed.mkdir()
        for name, value in (("tmp_dir_path", str(self.tmp)), ("extra_results_dir", str(self.extra))):
            patcher = patch.object(sym, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.markers = [f"COG{i:04d}" for i in range(56)]
        (self.tmp / "uni56_models.list").write_text("\n".join(self.markers) + "\n")

    def prepare_hits(self, genome_names, detected_markers):
        genome_ids = list(genome_names)
        (self.tmp / "genomes.list").write_text("\n".join(genome_ids) + "\n")
        (self.tmp / "genomes_dict.json").write_text(json.dumps(genome_names))
        lines = ["# Synthetic HMMER hits with duplicate domains and protein copies\n"]
        for genome_id, markers in detected_markers.items():
            proteins = {"protein_1": "original_protein", "protein_2": "second_copy"}
            (self.renamed / f"{genome_id}_dict.json").write_text(json.dumps(proteins))
            for marker in markers:
                lines.extend([
                    f"{genome_id}|protein_1 - {marker} - 1e-20 100\n",
                    f"{genome_id}|protein_1 - {marker} - 1e-20 100\n",
                    f"{genome_id}|protein_2 - {marker} - 1e-10 80\n",
                ])
        (self.tmp / "uni56_hmmsearch.tblout").write_text("".join(lines))
        sym.hmmer_results_to_pandas_df()

    def test_counts_missing_markers_and_original_ids_survive_cleanup(self):
        self.prepare_hits(
            {"genome_1": "partial_bin", "genome_2": "complete_bin", "genome_3": "no_hits"},
            {"genome_1": self.markers[:26], "genome_2": self.markers},
        )
        sym.count_uni56()
        internal = pd.read_csv(self.tmp / "uni56_presence.tsv", sep="\t").set_index("taxon_oid")
        self.assertEqual(internal.loc["genome_1", "total_UNI56"], 26)
        self.assertEqual(internal.loc["genome_1", "completeness_UNI56"], 46.43)
        self.assertEqual(internal.loc["genome_2", "completeness_UNI56"], 100)
        self.assertEqual(internal.loc["genome_3", "completeness_UNI56"], 0)

        sym.remove_temp_files()
        self.assertFalse(self.tmp.exists())
        presence = pd.read_csv(self.extra / "uni56_presence.tsv", sep="\t", keep_default_na=False)
        presence = presence.set_index("taxon_oid")
        self.assertEqual(presence.loc["partial_bin", "missing_markers"], ";".join(self.markers[26:]))
        self.assertEqual(presence.loc["complete_bin", "missing_markers"], "")
        self.assertEqual(presence.loc["no_hits", "missing_markers"], ";".join(self.markers))
        self.assertEqual(presence.loc["partial_bin", self.markers].sum(), 26)
        copies = pd.read_csv(self.extra / "uni56_copy_number.tsv", sep="\t").set_index("taxon_oid")
        self.assertEqual(list(copies.columns), self.markers)
        self.assertTrue(copies.loc["partial_bin", self.markers[:26]].eq(2).all())
        self.assertTrue(copies.loc["partial_bin", self.markers[26:]].eq(0).all())
        self.assertTrue(copies.loc["complete_bin"].eq(2).all())
        self.assertTrue(copies.loc["no_hits"].eq(0).all())
        pd.testing.assert_frame_equal(copies.gt(0).astype(int), presence[self.markers])
        hits = pd.read_csv(self.extra / "uni56_hits.tsv", sep="\t")
        self.assertEqual(len(hits), 2 * (26 + 56))
        self.assertEqual(set(hits.taxon_oid), {"partial_bin", "complete_bin"})
        self.assertEqual(set(hits.protein_name), {"original_protein", "second_copy"})
        self.assertEqual(set(hits.score), {80, 100})
        self.assertEqual(set(hits.evalue), {1e-10, 1e-20})

    def test_no_hits_still_exports_all_markers_and_empty_hits_table(self):
        self.prepare_hits({"genome_1": "empty_bin"}, {})
        sym.count_uni56()
        presence = pd.read_csv(self.extra / "uni56_presence.tsv", sep="\t")
        self.assertEqual(presence.loc[0, "total_UNI56"], 0)
        self.assertEqual(presence.loc[0, "completeness_UNI56"], 0)
        self.assertEqual(presence.loc[0, "missing_markers"], ";".join(self.markers))
        hits = pd.read_csv(self.extra / "uni56_hits.tsv", sep="\t")
        self.assertTrue(hits.empty)
        self.assertEqual(
            list(hits.columns),
            ["taxon_oid", "model", "evalue", "score", "protein_name", "protein_record_index"],
        )
        copies = pd.read_csv(self.extra / "uni56_copy_number.tsv", sep="\t").set_index("taxon_oid")
        self.assertEqual(list(copies.columns), self.markers)
        self.assertTrue(copies.loc["empty_bin"].eq(0).all())

    def test_copy_number_preserves_records_with_duplicate_input_identifiers(self):
        self.prepare_hits({"genome_1": "bin"}, {"genome_1": self.markers[:1]})
        (self.renamed / "genome_1_dict.json").write_text(json.dumps({
            "protein_1": "same_header", "protein_2": "same_header",
        }))
        sym.count_uni56()
        copies = pd.read_csv(self.extra / "uni56_copy_number.tsv", sep="\t")
        self.assertEqual(copies.loc[0, self.markers[0]], 2)
        hits = pd.read_csv(self.extra / "uni56_hits.tsv", sep="\t")
        self.assertEqual(hits.protein_name.tolist(), ["same_header", "same_header"])
        self.assertEqual(set(hits.protein_record_index), {1, 2})

    def test_single_copy_and_nonpositive_hits_match_presence(self):
        self.prepare_hits({"genome_1": "bin"}, {"genome_1": self.markers[:1]})
        tblout = self.tmp / "uni56_hmmsearch.tblout"
        lines = [line for line in tblout.read_text().splitlines(True) if "|protein_2 " not in line]
        lines.extend([
            f"genome_1|protein_1 - {self.markers[1]} - 1 0\n",
            f"genome_1|protein_2 - {self.markers[1]} - 1 -5\n",
        ])
        tblout.write_text("".join(lines))
        sym.hmmer_results_to_pandas_df()
        sym.count_uni56()
        copies = pd.read_csv(self.extra / "uni56_copy_number.tsv", sep="\t").set_index("taxon_oid")
        self.assertEqual(copies.loc["bin", self.markers[0]], 1)
        self.assertTrue(copies.loc["bin", self.markers[1:]].eq(0).all())
        presence = pd.read_csv(self.extra / "uni56_presence.tsv", sep="\t").set_index("taxon_oid")
        pd.testing.assert_frame_equal(copies.gt(0).astype(int), presence[self.markers])
        self.assertEqual(presence.loc["bin", "completeness_UNI56"], 1.79)

    def test_nonpositive_scores_do_not_reduce_completeness(self):
        self.prepare_hits({"genome_1": "bin"}, {"genome_1": self.markers[:1]})
        matrix_path = self.tmp / "uni56_hits_all_models.tsv"
        matrix = pd.read_csv(matrix_path, sep="\t")
        matrix.loc[0, self.markers[1]] = -5
        matrix.to_csv(matrix_path, sep="\t", index=False)
        sym.count_uni56()
        presence = pd.read_csv(self.extra / "uni56_presence.tsv", sep="\t")
        self.assertEqual(presence.loc[0, "total_UNI56"], 1)
        self.assertEqual(presence.loc[0, "completeness_UNI56"], 1.79)
        self.assertEqual(presence.loc[0, self.markers[1]], 0)


if __name__ == "__main__":
    unittest.main()
