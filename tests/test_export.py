# SPDX-License-Identifier: AGPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from topo_agent_mcp.export import BEGIN, END, export_repo
from topo_agent_mcp.store import Store


class ExportTests(unittest.TestCase):
    def test_export_preserves_manual_history_and_refreshes_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "topo_agent").mkdir()
            (root / "topo_agent" / "eval.py").write_text("", encoding="utf-8")
            (root / "docs").mkdir()
            experiments = root / "docs" / "experiments.md"
            experiments.write_text("# Experiments\n\nManual history stays.\n", encoding="utf-8")
            store = Store(root / "out" / "db.sqlite3")
            store.add_experiment("Alex", "Fast | careful", "Observed a gain", "abc1234", ["speed"])
            store.add_run("Alex", "method", "abc1234", "notes", "v1",
                          {"f1": 0.6, "recall": 0.5, "precision": 0.75, "seconds": 2.1}, [])
            benchmark = SimpleNamespace(version="v1")
            export_repo(store, benchmark, root)
            first = experiments.read_text(encoding="utf-8")
            board = (root / "docs" / "leaderboard.md").read_text(encoding="utf-8")
            self.assertIn("Manual history stays.", first)
            self.assertIn("Fast | careful", first)
            self.assertIn("60.0%", board)
            self.assertIn("2.1", board)
            export_repo(store, benchmark, root)
            self.assertEqual(first, experiments.read_text(encoding="utf-8"))
            self.assertEqual(first.count(BEGIN), 1)
            self.assertEqual(first.count(END), 1)

    def test_invalid_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "topo-agent checkout"):
                export_repo(Store(Path(directory) / "db.sqlite3"),
                            SimpleNamespace(version="v1"), directory)
