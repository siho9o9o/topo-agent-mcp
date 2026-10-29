# SPDX-License-Identifier: AGPL-3.0-or-later
import os
import unittest
from pathlib import Path

from topo_agent_mcp.benchmark import Benchmark


ROOT = Path(os.environ.get("TOPO_AGENT_ROOT", Path(__file__).resolve().parents[2] / "topo-agent"))
DATA = os.environ.get("TOPO_MCP_DATA_DIR")


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.benchmark = Benchmark(ROOT, DATA)

    def test_full_manifest_and_shared_evaluator(self):
        benchmark = self.benchmark
        self.assertEqual(benchmark.info()["images"], 8)
        self.assertEqual(benchmark.info()["routes"], 68)
        rows = [{"case_id": item["id"], "holds": item["marks"]["marks"],
                 "seconds": 1.234} for item in benchmark.items]
        metrics, scored = benchmark.score(rows)
        self.assertEqual(metrics["problems"], 68)
        self.assertEqual(metrics["seconds"], 1.2)
        self.assertEqual(metrics["hits"], sum(row["hits"] for row in scored))
        self.assertEqual(metrics["recall"], 0.993)

    def test_incomplete_and_duplicate_runs_are_rejected(self):
        benchmark = self.benchmark
        rows = [{"case_id": item["id"], "holds": [], "seconds": 1}
                for item in benchmark.items]
        with self.assertRaisesRegex(ValueError, "exactly"):
            benchmark.score(rows[:-1])
        rows[-1] = rows[0]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            benchmark.score(rows)

    def test_invalid_hold_and_time_are_rejected(self):
        benchmark = self.benchmark
        rows = [{"case_id": item["id"], "holds": [], "seconds": 1}
                for item in benchmark.items]
        rows[0]["seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "seconds"):
            benchmark.score(rows)
        rows[0]["seconds"] = 1
        rows[0]["holds"] = [{"x": 2, "y": 0.5, "r": 0.01}]
        with self.assertRaisesRegex(ValueError, "normalized"):
            benchmark.score(rows)
