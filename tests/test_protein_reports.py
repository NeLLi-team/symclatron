import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from symclatron import symclatron as sym


class FeatureProteinReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.tmp = root / "tmp"
        self.tmp.mkdir()
        self.extra = root / "extra_results"
        self.extra.mkdir()
        renamed = self.tmp / "renamed_genomes"
        renamed.mkdir()
        self.prefix = "symclatron_2384_union_features"
        self.genomes = {"genome_1": "sample_A", "genome_2": "sample_B"}
        (self.tmp / "genomes_dict.json").write_text(json.dumps(self.genomes))
        (self.tmp / "genomes.list").write_text("genome_1\ngenome_2\n")
        (self.tmp / f"{self.prefix}_models.list").write_text("OG0001\nOG0002\nOG0003\n")
        (renamed / "genome_1_dict.json").write_text(json.dumps({
            "protein_1": "sp|P00001|ORIGINAL", "protein_2": "repeated_ID", "protein_3": "repeated_ID",
        }))
        (renamed / "genome_2_dict.json").write_text(json.dumps({"protein_1": "other_original"}))
        for name, value in (("tmp_dir_path", str(self.tmp)), ("extra_results_dir", str(self.extra))):
            patcher = patch.object(sym, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_proteins_explain_feature_scores_after_cleanup(self):
        (self.tmp / f"{self.prefix}_hmmsearch.tblout").write_text(
            "genome_1|protein_1 - OG0001 - 1e-20 100\n"
            "genome_1|protein_1 - OG0001 - 1e-20 100\n"  # repeated domain
            "genome_1|protein_2 - OG0001 - 1e-20 100\n"  # tied best protein
            "genome_1|protein_3 - OG0001 - 1e-10 80\n"  # same original ID, separate record
            "genome_1|protein_3 - OG0002 - 100 -2\n"    # negative scores are retained
            "genome_2|protein_1 - OG0001 - 1e-15 75\n"
        )
        sym.hmmer_results_to_pandas_df()
        intermediate = self.tmp / f"{self.prefix}_hits_with_protein_names.tsv"
        original_intermediate = intermediate.read_bytes()
        matrix = pd.read_csv(self.tmp / f"{self.prefix}_hits_all_models.tsv", sep="\t")
        sym.save_feature_hits()
        self.assertEqual(intermediate.read_bytes(), original_intermediate)
        sym.remove_temp_files()

        hits = pd.read_csv(self.extra / "feature_hits.tsv", sep="\t")
        self.assertFalse(self.tmp.exists())
        self.assertEqual(len(hits), 5)
        self.assertEqual(set(hits.taxon_oid), {"sample_A", "sample_B"})
        self.assertNotIn("OG0003", set(hits.model))
        first_feature = hits[(hits.taxon_oid == "sample_A") & (hits.model == "OG0001")]
        self.assertEqual(first_feature.score.tolist(), [100, 80, 100])
        self.assertEqual(first_feature.protein_name.tolist(), ["repeated_ID", "repeated_ID", "sp|P00001|ORIGINAL"])
        self.assertEqual(first_feature.protein_record_index.tolist(), [2, 3, 1])
        self.assertEqual(first_feature.is_best_hit.tolist(), [True, False, True])
        self.assertEqual(hits.loc[hits.taxon_oid == "sample_B", "protein_name"].tolist(), ["other_original"])
        negative = hits.loc[hits.model == "OG0002"].iloc[0]
        self.assertEqual(negative.score, -2)
        self.assertTrue(negative.is_best_hit)

        matrix["taxon_oid"] = matrix["taxon_oid"].map(self.genomes)
        matrix = matrix.set_index("taxon_oid")
        for (genome, feature), proteins in hits.groupby(["taxon_oid", "model"]):
            self.assertEqual(proteins.score.max(), matrix.loc[genome, feature])
            self.assertTrue(proteins.loc[proteins.is_best_hit, "score"].eq(matrix.loc[genome, feature]).all())

    def test_no_hits_retains_report_headers_without_inventing_proteins(self):
        (self.tmp / f"{self.prefix}_hmmsearch.tblout").write_text("# No hits\n")
        sym.hmmer_results_to_pandas_df()
        sym.save_feature_hits()
        sym.remove_temp_files()
        hits = pd.read_csv(self.extra / "feature_hits.tsv", sep="\t")
        self.assertTrue(hits.empty)
        self.assertEqual(
            hits.columns.tolist(),
            ["taxon_oid", "model", "evalue", "score", "protein_name", "is_best_hit", "protein_record_index"],
        )

    def test_identical_original_ids_and_scores_keep_distinct_record_numbers(self):
        (self.tmp / f"{self.prefix}_hmmsearch.tblout").write_text(
            "genome_1|protein_2 - OG0001 - 1e-20 100\n"
            "genome_1|protein_3 - OG0001 - 1e-20 100\n"
        )
        sym.hmmer_results_to_pandas_df()
        sym.save_feature_hits()
        sym.remove_temp_files()
        hits = pd.read_csv(self.extra / "feature_hits.tsv", sep="\t")
        self.assertEqual(hits.protein_name.tolist(), ["repeated_ID", "repeated_ID"])
        self.assertEqual(set(hits.protein_record_index), {2, 3})
        self.assertTrue(hits.is_best_hit.all())


if __name__ == "__main__":
    unittest.main()
