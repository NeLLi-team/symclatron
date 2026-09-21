import io
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import typer

from symclatron import symclatron as sym


class DatabaseSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        self.package.mkdir()
        self.data = self.package / "data"
        self.data.mkdir()
        (self.data / "old-model").write_text("working database")
        self.archive = self.root / "database.tar.gz"
        patcher = patch.object(sym, "script_dir", str(self.package))
        patcher.start()
        self.addCleanup(patcher.stop)
        output = patch.object(sym.typer, "secho")
        output.start()
        self.addCleanup(output.stop)

    def make_archive(self, entries):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, contents in entries.items():
                member = tarfile.TarInfo(name)
                if contents is None:
                    member.type = tarfile.DIRTYPE
                    archive.addfile(member)
                else:
                    encoded = contents.encode()
                    member.size = len(encoded)
                    archive.addfile(member, io.BytesIO(encoded))

    def download(self, url, target):
        shutil.copyfile(self.archive, target)
        return target, None

    def assert_old_database_preserved(self):
        self.assertEqual((self.data / "old-model").read_text(), "working database")
        self.assertEqual(sorted(path.name for path in self.package.iterdir()), ["data"])

    def test_existing_database_without_force_does_not_download(self):
        with patch.object(sym.urllib.request, "urlretrieve") as download:
            sym.extract_data(quiet=True)
        download.assert_not_called()
        self.assert_old_database_preserved()

    def test_failed_download_preserves_database(self):
        with patch.object(sym.urllib.request, "urlretrieve", side_effect=OSError("offline")):
            with self.assertRaises(typer.Exit):
                sym.extract_data(force=True, quiet=True)
        self.assert_old_database_preserved()

    def test_checksum_mismatch_preserves_database(self):
        self.make_archive({"data/new-model": "replacement"})
        with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
            with self.assertRaises(typer.Exit):
                sym.extract_data(force=True, quiet=True, data_sha256="0" * 64)
        self.assert_old_database_preserved()

    def test_invalid_archive_preserves_database(self):
        self.archive.write_text("not a tar archive")
        with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
            with self.assertRaises(typer.Exit):
                sym.extract_data(force=True, quiet=True)
        self.assert_old_database_preserved()

    def test_missing_or_empty_data_directory_is_rejected(self):
        for entries in ({"unrelated.txt": "not a database"}, {"data": None}):
            with self.subTest(entries=entries):
                self.make_archive(entries)
                with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
                    with self.assertRaises(typer.Exit):
                        sym.extract_data(force=True, quiet=True)
                self.assert_old_database_preserved()

    def test_successful_replacement_supports_both_archive_layouts(self):
        for prefix in ("data", "symclatron_db/data"):
            with self.subTest(prefix=prefix):
                self.make_archive({f"{prefix}/new-model": "replacement", "unrelated.txt": "ignored"})
                with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
                    sym.extract_data(force=True, quiet=True)
                self.assertEqual((self.data / "new-model").read_text(), "replacement")
                self.assertFalse((self.data / "old-model").exists())
                self.assertEqual(sorted(path.name for path in self.package.iterdir()), ["data"])

    def test_first_install_creates_data_directory(self):
        shutil.rmtree(self.data)
        self.make_archive({"symclatron_db/data/new-model": "replacement"})
        with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
            sym.extract_data(quiet=True)
        self.assertEqual((self.data / "new-model").read_text(), "replacement")
        self.assertEqual(sorted(path.name for path in self.package.iterdir()), ["data"])

    def test_replacing_symlink_preserves_shared_database(self):
        shared_data = self.root / "shared-data"
        self.data.rename(shared_data)
        self.data.symlink_to(shared_data, target_is_directory=True)
        self.make_archive({"data/new-model": "replacement"})
        with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
            sym.extract_data(force=True, quiet=True)
        self.assertEqual((self.data / "new-model").read_text(), "replacement")
        self.assertFalse(self.data.is_symlink())
        self.assertEqual((shared_data / "old-model").read_text(), "working database")

    def test_failed_install_restores_database(self):
        self.make_archive({"data/new-model": "replacement"})
        original_replace = sym.os.replace

        def fail_install(source, destination):
            if Path(source).parent.name == "extracted" and Path(destination) == self.data:
                raise OSError("simulated install failure")
            return original_replace(source, destination)

        with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
            with patch.object(sym.os, "replace", side_effect=fail_install):
                with self.assertRaises(typer.Exit):
                    sym.extract_data(force=True, quiet=True)
        self.assert_old_database_preserved()

    def test_failed_rollback_keeps_recoverable_backup(self):
        self.make_archive({"data/new-model": "replacement"})
        original_replace = sym.os.replace

        def fail_install_and_rollback(source, destination):
            if Path(destination) == self.data:
                raise OSError("simulated install and rollback failure")
            return original_replace(source, destination)

        with patch.object(sym.urllib.request, "urlretrieve", side_effect=self.download):
            with patch.object(sym.os, "replace", side_effect=fail_install_and_rollback):
                with self.assertRaises(typer.Exit):
                    sym.extract_data(force=True, quiet=True)
        backups = list(self.package.glob(".symclatron-setup-*/previous-data/old-model"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "working database")


class SafeExtractionTests(unittest.TestCase):
    def test_archive_symlink_cannot_redirect_later_file_outside_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "extracted"
            destination.mkdir()
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "model"
            sentinel.write_text("original")
            archive_path = root / "archive.tar"
            with tarfile.open(archive_path, "w") as archive:
                link = tarfile.TarInfo("escape")
                link.type = tarfile.SYMTYPE
                link.linkname = "../outside"
                archive.addfile(link)
                payload = tarfile.TarInfo("escape/model")
                payload.size = len(b"overwritten")
                archive.addfile(payload, io.BytesIO(b"overwritten"))

            with self.assertRaises((tarfile.FilterError, RuntimeError)):
                sym._safe_extract_tar(str(archive_path), str(destination))
            self.assertEqual(sentinel.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
