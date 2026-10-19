import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import filesentinel as fs


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "data"
        self.root.mkdir()

    def test_changes_additions_and_removals(self):
        (self.root / "change").write_text("before", encoding="utf-8")
        (self.root / "remove").write_bytes(b"remove")
        before = fs.snapshot(self.root)
        (self.root / "change").write_text("after", encoding="utf-8")
        (self.root / "remove").unlink()
        (self.root / "add").write_bytes(b"new")
        self.assertEqual(fs.compare(before, fs.snapshot(self.root)), {"added": ["add"], "removed": ["remove"], "changed": ["change"], "unchanged": 0})

    def test_unicode_and_empty_file(self):
        (self.root / "заметки.txt").write_bytes(b"")
        manifest = fs.snapshot(self.root)
        path = self.directory / "snapshot.json"
        fs.save_manifest(path, manifest)
        self.assertEqual(fs.load_manifest(path), manifest)
        self.assertEqual(manifest["files"]["заметки.txt"]["sha256"], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_same_size_content_changes_are_detected(self):
        path = self.root / "same-size"
        path.write_bytes(b"aaaa")
        before = fs.snapshot(self.root)
        path.write_bytes(b"bbbb")
        self.assertEqual(fs.compare(before, fs.snapshot(self.root))["changed"], ["same-size"])

    def test_skipped_links_do_not_get_hashed(self):
        path = self.root / "simulated-link"
        path.write_bytes(b"x")
        original = fs.is_link
        with patch.object(fs, "is_link", side_effect=lambda candidate: candidate == path or original(candidate)):
            with patch.object(fs, "digest_file", side_effect=AssertionError("link must not be read")):
                manifest = fs.snapshot(self.root)
        self.assertEqual(manifest["skipped"], ["simulated-link"])

    def test_exclusions_and_unchanged(self):
        (self.root / "cache").mkdir()
        (self.root / "cache" / "item").write_bytes(b"x")
        (self.root / "keep.txt").write_bytes(b"y")
        manifest = fs.snapshot(self.root, ["cache/**"])
        self.assertEqual(list(manifest["files"]), ["keep.txt"])
        self.assertEqual(fs.compare(manifest, manifest)["unchanged"], 1)
        with self.assertRaisesRegex(ValueError, "different exclusions"):
            fs.compare(manifest, fs.snapshot(self.root))

    def test_read_error_never_produces_baseline(self):
        (self.root / "blocked").write_bytes(b"x")
        with patch.object(fs, "digest_file", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                fs.snapshot(self.root)

    def test_manifest_validation_and_duplicate_keys(self):
        manifest = fs.snapshot(self.root)
        manifest["files"]["../outside"] = {"sha256": "0" * 64, "size": 1}
        with self.assertRaises(ValueError):
            fs.validate_manifest(manifest)
        path = self.directory / "bad.json"
        path.write_text('{"files":{},"files":{}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            fs.load_manifest(path)

    def test_symlinks_are_skipped(self):
        target = self.directory / "outside"
        target.write_bytes(b"secret")
        try:
            os.symlink(target, self.root / "link")
        except OSError:
            self.skipTest("symlink creation unavailable on this host")
        manifest = fs.snapshot(self.root)
        self.assertEqual(manifest["files"], {})
        self.assertEqual(manifest["skipped"], ["link"])

    def test_detects_file_changed_during_hashing(self):
        path = self.root / "changing"
        path.write_bytes(b"before")
        original = fs.hashlib.file_digest
        def mutate(stream, algorithm):
            result = original(stream, algorithm)
            path.write_bytes(b"after content")
            return result
        with patch.object(fs.hashlib, "file_digest", side_effect=mutate):
            with self.assertRaises(OSError):
                fs.digest_file(path)

    def test_cli_exit_codes_and_inside_root_rejection(self):
        baseline = self.directory / "before.json"
        after = self.directory / "after.json"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(fs.main(["snapshot", str(self.root), "-o", str(baseline)]), 0)
            self.assertEqual(fs.main(["snapshot", str(self.root), "-o", str(self.root / "bad.json")]), 2)
            self.assertEqual(fs.main(["compare", str(baseline), str(baseline), "--json"]), 0)
            (self.root / "new").write_bytes(b"x")
            self.assertEqual(fs.main(["snapshot", str(self.root), "-o", str(after)]), 0)
            self.assertEqual(fs.main(["compare", str(baseline), str(after)]), 1)
            self.assertEqual(fs.main(["compare", str(self.directory / "missing"), str(after)]), 2)


if __name__ == "__main__":
    unittest.main()
