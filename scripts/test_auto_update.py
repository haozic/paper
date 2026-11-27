"""Check cross-year planning and release metadata without touching the repository."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_update
import update_readme_data


class AutoUpdateTests(unittest.TestCase):
    def test_missing_issues_crosses_year_without_skipping(self):
        self.assertEqual(
            auto_update.missing_issues((2026, 22), (2027, 2), 24),
            [(2026, 23), (2026, 24), (2027, 1), (2027, 2)],
        )

    def test_version_and_about_are_updated_in_isolated_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*auto_update.VERSION_FILES, "scripts/build_search_index.py", "README.md"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(auto_update.ROOT / name, target)
            for key, path in (("qs", "data/qs/meta.json"), ("hqwg", "data/hqwg/meta.json"),
                              ("djyj", "data/meta.json"), ("qz", "data/qz/meta.json")):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps([{"y": 2027, "i": 1}]), encoding="utf-8")
            speech_index = root / "data/speeches/index.json"
            speech_index.parent.mkdir(parents=True, exist_ok=True)
            speech_index.write_text(json.dumps({"items": [{"y": 2027, "p": "body.md"}, {"y": 2012, "p": None}]}), encoding="utf-8")
            (root / "data/counts.json").write_text(json.dumps({key: {"articles": 1, "issues": 1}
                                                                 for key in ("qs", "hqwg", "djyj", "qz")}), encoding="utf-8")
            with patch.object(auto_update, "ROOT", root):
                version = auto_update.new_version()
                next_version = auto_update.new_version()
                auto_update.update_about()
            with patch.object(update_readme_data, "ROOT", root):
                self.assertTrue(update_readme_data.update())
                self.assertFalse(update_readme_data.update(check=True))
            self.assertGreater(next_version, version)
            self.assertIn(next_version, (root / "speeches/speeches.js").read_text("utf-8"))
            self.assertIn(f"INDEX_VERSION = '{next_version}'", (root / "scripts/build_search_index.py").read_text("utf-8"))
            self.assertIn("2027 年第 1 期", (root / "index.html").read_text("utf-8"))
            self.assertIn("2012 年至 2027 年，2 条目录记录；1 篇可阅读正文", (root / "index.html").read_text("utf-8"))
            self.assertIn("2 篇 · 2012—2027", (root / "index.html").read_text("utf-8"))
            readme = (root / "README.md").read_text("utf-8")
            self.assertIn("2027 年第 1 期 | 1 | 1 |", readme)
            self.assertIn("讲话库有 1 篇已归档正文、1 篇官网原文暂不可读取", readme)
            (root / "data/counts.json").write_text(json.dumps({"qs": {"articles": 2, "issues": 1}}), encoding="utf-8")
            with patch.object(update_readme_data, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "Counts and catalog disagree"):
                    update_readme_data.update(check=True)


if __name__ == "__main__":
    unittest.main()
