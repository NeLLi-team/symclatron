import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from symclatron import symclatron as sym


class HmmResultPathTests(unittest.TestCase):
    def test_hmm_tables_preserve_literal_parent_directory_names(self):
        for directory in ("batch[1]", "batch_hmmsearch.tblout", "ordinary"):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as root:
                tmp = Path(root) / directory
                tmp.mkdir()
                (tmp / "genomes.list").write_text("genome_1\ngenome_2\n")
                (tmp / "uni56_models.list").write_text("COG0001\nCOG0002\n")
                (tmp / "uni56_hmmsearch.tblout").write_text(
                    "genome_1|protein_1 - COG0001 - 1e-20 100\n"
                )
                with patch.object(sym, "tmp_dir_path", str(tmp), create=True):
                    sym.hmmer_results_to_pandas_df()
                matrix = pd.read_csv(tmp / "uni56_hits_all_models.tsv", sep="\t")
                matrix = matrix.set_index("taxon_oid")
                self.assertEqual(matrix.loc["genome_1", "COG0001"], 100)
                self.assertEqual(matrix.loc["genome_1", "COG0002"], 0)
                self.assertTrue(matrix.loc["genome_2"].eq(0).all())
                hits = pd.read_csv(tmp / "uni56_hits_with_protein_names.tsv", sep="\t")
                self.assertEqual(hits.protein_name.tolist(), ["protein_1"])


class GenomeReportTests(unittest.TestCase):
    def test_auxiliary_reports_keep_original_genome_ids_after_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            tmp = Path(root) / "tmp"
            tmp.mkdir()
            extra = Path(root) / "extra_results"
            extra.mkdir()
            internal_ids = ["genome_2", "genome_1"]
            original_ids = ["my.second.bin", "my_first_bin"]
            (tmp / "genomes_dict.json").write_text(json.dumps(dict(zip(internal_ids, original_ids))))
            features = pd.DataFrame({
                "taxon_oid": internal_ids,
                "OG0001": [20.0, 40.0],
                "OG0002": [1.0, 2.0],
            })
            for name in ("symcla", "symreg", "hostcla"):
                features.to_csv(tmp / f"{name}_hits_all_models.tsv", sep="\t", index=False)

            regressor = MagicMock()
            regressor.predict.return_value = np.array([0.1, 0.2])
            symcla = MagicMock()
            symcla.predict_proba.return_value = np.array([[0.7, 0.2, 0.1], [0.2, 0.7, 0.1]])
            hostcla = MagicMock()
            hostcla.predict_proba.return_value = np.array([[0.8, 0.2], [0.3, 0.7]])
            xgb = SimpleNamespace(
                XGBRegressor=MagicMock(return_value=regressor),
                XGBClassifier=MagicMock(side_effect=[symcla, hostcla]),
            )
            shap_values = np.array([[0.01, 0.09], [0.05, 0.15]])
            explainer = MagicMock(return_value=SimpleNamespace(values=shap_values))
            with patch.object(sym, "tmp_dir_path", str(tmp), create=True), patch.object(
                sym, "extra_results_dir", str(extra)
            ), patch.object(sym, "_import_xgboost", return_value=xgb), patch.object(
                sym, "_ensure_xgb_estimator_type"
            ), patch.object(sym, "_build_shap_explainer", return_value=explainer):
                sym.classify_genomes_internal()
                sym.compute_feature_contribution()
                for name in ("symcla", "symreg", "hostcla"):
                    intermediate = pd.read_csv(tmp / f"{name}_predictions.tsv", sep="\t")
                    self.assertEqual(intermediate.taxon_oid.tolist(), internal_ids)
                sym.remove_temp_files()

            self.assertFalse(tmp.exists())
            for name in ("bitscore_symcla", "bitscore_symreg", "bitscore_hostcla", "shap_symreg"):
                with self.subTest(report=name):
                    report = pd.read_csv(extra / f"{name}.tsv", sep="\t")
                    self.assertEqual(report.taxon_oid.tolist(), original_ids)
            melted = pd.read_csv(extra / "shap_melt_symreg.tsv", sep="\t")
            self.assertEqual(melted.taxon_oid.tolist(), [original_ids[0]] * 2 + [original_ids[1]] * 2)
            shap_report = pd.read_csv(extra / "shap_symreg.tsv", sep="\t")
            np.testing.assert_allclose(shap_report[["OG0001", "OG0002"]], shap_values)


class WeightedDistanceTests(unittest.TestCase):
    def test_distances_align_features_with_training_columns(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            arrays = root_path / "data" / "arrays"
            arrays.mkdir(parents=True)
            tmp = root_path / "tmp"
            tmp.mkdir()
            for model in ("REG", "CLA"):
                pd.DataFrame({"feature": ["OG0002", "OG0001"], "importance": [9.0, 4.0]}).to_csv(
                    arrays / f"feature_importance_{model}.tsv", sep="\t", index=False
                )
                pd.DataFrame({"taxon_oid": ["reference"], "OG0001": [3.0], "OG0002": [10.0]}).to_csv(
                    arrays / f"array_{model}.tsv", sep="\t", index=False
                )
                # Feature order differs from the training set; an identical row
                # must still have zero distance, and offsets (1, 2) give sqrt(40).
                pd.DataFrame({
                    "taxon_oid": ["identical", "offset"],
                    "OG0002": [10.0, 12.0],
                    "OG0001": [3.0, 4.0],
                }).to_csv(tmp / f"sym{model.lower()}_hits_all_models.tsv", sep="\t", index=False)
            with patch.object(sym, "tmp_dir_path", str(tmp), create=True), patch.object(
                sym, "script_dir", str(root_path)
            ):
                sym.calculate_weighted_distances()
            for model in ("REG", "CLA"):
                distances = pd.read_csv(tmp / f"min_distances_{model.lower()}.tsv", sep="\t")
                np.testing.assert_allclose(distances[f"min_distance_weighted_{model}"], [0, np.sqrt(40)])


if __name__ == "__main__":
    unittest.main()
