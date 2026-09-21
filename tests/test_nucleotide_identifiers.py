import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from symclatron import symclatron as sym


class NucleotideIdentifierTests(unittest.TestCase):
    def test_translated_cds_retains_original_ids_without_changing_proteins(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            cds = directory / "genes.ffn"
            cds.write_text(
                ">CDS_A first annotation\nATGCCAGAAAAATAA\n"
                ">CDS_A duplicate identifier\nATGTTTCCATAA\n"
                ">CDS_B third annotation\nATGGGCTAA\n"
            )
            proteins = directory / "genome_1.faa"
            info = sym._translate_genes_to_proteins(cds, proteins)
            expected_sequences = ["MPEK", "MFP", "MG"]
            records = list(sym._parse_fasta(proteins))
            self.assertEqual(info["proteins"], 3)
            self.assertEqual([header for header, _ in records], [
                "CDS_A first annotation", "CDS_A duplicate identifier", "CDS_B third annotation",
            ])
            self.assertEqual([sequence for _, sequence in records], expected_sequences)

            sym.rename_all_proteins_in_fasta_files(str(directory), str(directory))
            self.assertEqual(
                json.loads((directory / "genome_1_dict.json").read_text()),
                {"protein_1": "CDS_A", "protein_2": "CDS_A", "protein_3": "CDS_B"},
            )
            renamed_records = list(sym._parse_fasta(proteins))
            self.assertEqual([sequence for _, sequence in renamed_records], expected_sequences)
            self.assertEqual(len({header for header, _ in renamed_records}), 3)

    def test_contig_description_does_not_hide_predicted_gene_identifiers(self):
        # Match Pyrodigal's use of sequence_id: each gene gets an _N suffix.
        # A description in sequence_id would put that suffix after whitespace.
        class PredictedGenes:
            def __len__(self):
                return 2

            def write_translations(self, handle, sequence_id, **kwargs):
                for index, sequence in enumerate(("MPEPTIDE", "MELT"), 1):
                    handle.write(f">{sequence_id}_{index} # predicted gene\n{sequence}\n")

        with tempfile.TemporaryDirectory() as root:
            observed_records = []
            for suffix in ("", " description with spaces"):
                with self.subTest(description=suffix):
                    directory = Path(root) / ("described" if suffix else "plain")
                    directory.mkdir()
                    contigs = directory / "contigs.fna"
                    sequence = "ATGCCAGAAAAATAA"
                    contigs.write_text(f">contigA{suffix}\n{sequence}\n")
                    proteins = directory / "genome_1.faa"
                    finder = Mock()
                    finder.find_genes.return_value = PredictedGenes()
                    gene_finder = Mock(return_value=finder)
                    pyrodigal = SimpleNamespace(GeneFinder=gene_finder)
                    with patch.dict("sys.modules", {"pyrodigal": pyrodigal}):
                        info = sym._predict_proteins_with_pyrodigal(contigs, proteins)
                    gene_finder.assert_called_once_with(meta=True, mask=True)
                    finder.find_genes.assert_called_once_with(sequence)
                    self.assertEqual(info["genes"], 2)
                    observed_records.append(list(sym._parse_fasta(proteins)))

                    sym.rename_all_proteins_in_fasta_files(str(directory), str(directory))
                    self.assertEqual(
                        json.loads((directory / "genome_1_dict.json").read_text()),
                        {"protein_1": "contigA_1", "protein_2": "contigA_2"},
                    )
                    self.assertEqual(
                        [protein for _, protein in sym._parse_fasta(proteins)],
                        ["MPEPTIDE", "MELT"],
                    )
            self.assertEqual(observed_records[0], observed_records[1])


if __name__ == "__main__":
    unittest.main()
