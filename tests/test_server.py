# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from topo_agent_mcp.app import _archive
from topo_agent_mcp.benchmark import Benchmark
from topo_agent_mcp.store import Store


ROOT = Path(os.environ.get("TOPO_AGENT_ROOT", Path(__file__).resolve().parents[2] / "topo-agent"))
DATA = os.environ.get("TOPO_MCP_DATA_DIR")
WRITE_TOKEN = "test-team-write-token-0123456789abcdef"


class StoreTests(unittest.TestCase):
    def test_experiment_and_run_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db.sqlite3"
            store = Store(path)
            note = store.add_experiment("Alex", "Faster SAM", "Cut inference time", "abc1234", ["latency"])
            store.add_run("Alex", "method", "abc1234", "details", "version", {"f1": 0.5}, [])
            reopened = Store(path)
            self.assertEqual(reopened.experiments("SAM")[0]["id"], note["id"])
            self.assertEqual(reopened.runs("version")[0]["metrics"]["f1"], 0.5)
            self.assertEqual(reopened.runs("other"), [])


class ServerTests(unittest.TestCase):
    def test_mcp_tools_and_dataset_archive(self):
        benchmark = Benchmark(ROOT, DATA)
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = {**os.environ, "TOPO_AGENT_ROOT": str(ROOT),
                   "TOPO_MCP_DATA_DIR": str(benchmark.data),
                   "TOPO_MCP_DB": str(Path(directory) / "db.sqlite3"),
                   "TOPO_MCP_OUT": str(Path(directory) / "out"),
                   "TOPO_MCP_PORT": str(port),
                   "TOPO_MCP_WRITE_TOKEN": WRITE_TOKEN,
                   "TOPO_MCP_PUBLIC_URL": f"http://127.0.0.1:{port}"}
            process = subprocess.Popen([sys.executable, "-m", "topo_agent_mcp.app"],
                                       cwd=directory, env=env, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE)
            try:
                for _ in range(60):
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                            self.assertIn(b"Leaderboard", response.read())
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail(f"Server did not start: {process.stderr.read().decode()}")
                asyncio.run(self._exercise_mcp(port, benchmark))
                archive = _archive(benchmark)
                with zipfile.ZipFile(archive) as zipped:
                    self.assertIn("annotations.json", zipped.namelist())
                    self.assertIn("SOURCES.md", zipped.namelist())
                    self.assertEqual(len([name for name in zipped.namelist() if name.endswith(".jpg")]), 8)
                    self.assertEqual(zipped.read("DATASET_VERSION.txt").decode().strip(), benchmark.version)
            finally:
                process.terminate()
                process.wait(timeout=10)
                process.stderr.close()

    async def _exercise_mcp(self, port, benchmark):
        url = f"http://127.0.0.1:{port}/mcp"
        async with Client(url) as client:
            tools = await client.list_tools()
            self.assertIn("get_dataset_download", [tool.name for tool in tools.tools])
            rules = (await client.call_tool("get_rules")).content[0].text
            self.assertIn("never push to main", rules)
            self.assertIn("pyflakes", rules)
            info = json.loads((await client.call_tool("get_benchmark")).content[0].text)
            self.assertEqual(info["routes"], 68)
            download = json.loads((await client.call_tool("get_dataset_download")).content[0].text)
            self.assertEqual(download["dataset_version"], benchmark.version)
            self.assertTrue(download["url"].endswith("/dataset/real_routes.zip"))
            with urllib.request.urlopen(download["url"], timeout=30) as response:
                self.assertEqual(download["sha256"], hashlib.sha256(response.read()).hexdigest())
            denied = await client.call_tool("submit_experiment", {"author": "Alex",
                "title": "Denied", "summary": "No token"})
            self.assertTrue(denied.is_error)
            self.assertEqual((await client.call_tool("search_experiments")).content, [])
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer invalid-token"}) as http:
            async with Client(streamable_http_client(url, http_client=http)) as client:
                denied = await client.call_tool("submit_experiment", {"author": "Alex",
                    "title": "Denied", "summary": "Wrong token"})
                self.assertTrue(denied.is_error)
        async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {WRITE_TOKEN}"}) as http:
            async with Client(streamable_http_client(url, http_client=http)) as client:
                note = await client.call_tool("submit_experiment", {"author": "Alex", "title": "Trial",
                    "summary": "Initial observation", "commit_sha": "abc1234", "tags": ["test"]})
                self.assertFalse(note.is_error)
                rows = [{"case_id": item["id"], "holds": [], "seconds": 0.2}
                        for item in benchmark.items]
                run = await client.call_tool("submit_run", {"author": "Alex", "method": "empty",
                    "commit_sha": "abc1234", "dataset_version": benchmark.version, "rows": rows})
                self.assertFalse(run.is_error)
                run_data = json.loads(run.content[0].text)
                self.assertEqual(run_data["metrics"]["recall"], 0)
                self.assertTrue(run_data["new_frontier_record"])
                leaderboard = json.loads((await client.call_tool("get_leaderboard")).content[0].text)
                self.assertEqual(len(leaderboard["runs"]), 1)
                self.assertEqual(leaderboard["frontier_run_ids"], [run_data["run_id"]])
                notes = await client.call_tool("search_experiments")
                self.assertEqual(len(notes.content), 2)
