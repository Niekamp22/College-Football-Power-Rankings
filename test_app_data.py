from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app_data import load_bytes, load_csv, load_json


class AppDataTests(unittest.TestCase):
    def test_unchanged_csv_is_read_once_and_callers_get_independent_copies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ratings.csv"
            path.write_text("team,rating\nAlpha,10\n", encoding="utf-8")
            with patch("app_data.pd.read_csv", wraps=pd.read_csv) as reader:
                first = load_csv(path)
                first.loc[0, "rating"] = 999
                second = load_csv(path)
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(second.loc[0, "rating"], 10)

    def test_rewritten_and_replaced_csv_files_invalidate_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ratings.csv"
            path.write_text("team,rating\nAlpha,10\n", encoding="utf-8")
            self.assertEqual(load_csv(path).loc[0, "rating"], 10)
            previous = path.stat()
            path.write_text("team,rating\nAlpha,20\n", encoding="utf-8")
            os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000_000))
            self.assertEqual(load_csv(path).loc[0, "rating"], 20)
            previous = path.stat()
            replacement = Path(directory) / "replacement.csv"
            replacement.write_text("team,rating\nAlpha,30\n", encoding="utf-8")
            os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            os.replace(replacement, path)
            self.assertEqual(load_csv(path).loc[0, "rating"], 30)

    def test_missing_file_does_not_hide_a_later_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.csv"
            self.assertTrue(load_csv(path).empty)
            path.write_text("team\nAlpha\n", encoding="utf-8")
            self.assertEqual(load_csv(path).loc[0, "team"], "Alpha")

    def test_json_and_downloads_refresh_when_files_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps({"week": 9}), encoding="utf-8")
            first = load_json(path)
            first["week"] = 999
            self.assertEqual(load_json(path)["week"], 9)
            self.assertIn(b"9", load_bytes(path))
            path.write_text(json.dumps({"week": 10}), encoding="utf-8")
            self.assertEqual(load_json(path)["week"], 10)
            self.assertIn(b"10", load_bytes(path))
            path.write_text("invalid json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load_json(path)


if __name__ == "__main__":
    unittest.main()
