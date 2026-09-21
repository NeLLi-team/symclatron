import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import typer

from symclatron import symclatron as sym


class ClassificationPathTests(unittest.TestCase):
    def test_reused_output_cannot_delete_input_in_its_temporary_directory(self):
        for input_form in ("directory", "file", "symlinked_file"):
            with self.subTest(input_form=input_form), tempfile.TemporaryDirectory() as root:
                root = Path(root)
                output = root / "results"
                inputs = output / "tmp" / "inputs"
                inputs.mkdir(parents=True)
                genome = inputs / "genome.faa"
                original = ">protein\nMPEPTIDE\n"
                genome.write_text(original)
                if input_form == "directory":
                    input_path = inputs
                elif input_form == "file":
                    input_path = genome
                else:
                    input_path = root / "genome.faa"
                    input_path.symlink_to(genome)

                # A failed run must leave user-supplied FASTA files intact.
                with patch.object(sym, "ResourceMonitor"), patch.object(sym, "setup_logging"):
                    with self.assertRaises(typer.Exit):
                        sym.classify(
                            genome_dir=str(input_path), save_dir=str(output),
                            input_kind="proteins", quiet=True,
                        )
                self.assertTrue(genome.exists(), "Classification deleted the input genome")
                self.assertEqual(genome.read_text(), original)

    def test_input_symlinks_inside_workspace_are_preserved(self):
        for input_form in ("file", "directory"):
            with self.subTest(input_form=input_form), tempfile.TemporaryDirectory() as root:
                root = Path(root)
                inputs = root / "inputs"
                inputs.mkdir()
                genome = inputs / "genome.faa"
                genome.write_text(">protein\nMPEPTIDE\n")
                output = root / "results"
                workspace = output / "tmp"
                workspace.mkdir(parents=True)
                link = workspace / "input.faa"
                link.symlink_to(genome if input_form == "file" else inputs)
                # The output is addressed through an alias, while the input is
                # addressed through its physical path inside that workspace.
                output_alias = root / "output-alias"
                output_alias.symlink_to(output)
                with patch.object(sym, "ResourceMonitor"), patch.object(sym, "setup_logging"):
                    with self.assertRaises(typer.Exit):
                        sym.classify(
                            genome_dir=str(link), save_dir=str(output_alias),
                            input_kind="proteins", quiet=True,
                        )
                self.assertTrue(link.is_symlink())
                self.assertEqual(genome.read_text(), ">protein\nMPEPTIDE\n")


if __name__ == "__main__":
    unittest.main()
