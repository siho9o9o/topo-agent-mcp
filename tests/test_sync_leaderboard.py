# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline integration tests for automatic leaderboard PR scope."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from topo_agent_mcp import sync_leaderboard
from topo_agent_mcp.store import Store


def git(*args, cwd=None):
    """Run Git in a temporary local repository."""
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


class SyncTests(unittest.TestCase):
    def test_creates_only_leaderboard_and_skips_unchanged_open_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "repo"
            git("init", "-q", "--bare", str(remote))
            git("init", "-q", "-b", "main", str(repo))
            (repo / "docs").mkdir()
            (repo / "docs" / "leaderboard.md").write_text("# Old snapshot\n", encoding="utf-8")
            (repo / "docs" / "experiments.md").write_text("# Manual history\n", encoding="utf-8")
            git("add", ".", cwd=repo)
            git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                "commit", "-qm", "Start", cwd=repo)
            git("remote", "add", "upstream", str(remote), cwd=repo)
            git("push", "-q", "upstream", "main", cwd=repo)
            store = Store(root / "db.sqlite3")
            store.add_run("Alex", "meta", "abc1234", "", "v1",
                          {"f1": 0.5, "recall": 0.5, "precision": 0.5,
                           "seconds": 2.0}, [])
            created = []
            real_run = sync_leaderboard._run

            def run(args, cwd=None):
                if args[:3] == ["gh", "pr", "create"]:
                    created.append(args)
                    return "https://example.invalid/pr/1"
                return real_run(args, cwd)

            with patch.object(sync_leaderboard, "_run", side_effect=run), \
                    patch.object(sync_leaderboard, "_pull_requests", return_value=[]):
                result = sync_leaderboard.sync_once(repo, "test/repo", "upstream",
                                                    "/bin/true", SimpleNamespace(version="v1"), store)
            self.assertEqual(result, "Created leaderboard-only PR")
            self.assertEqual(len(created), 1)
            changed = git("--git-dir", str(remote), "diff", "--name-only", "main...bot/leaderboard-snapshot")
            self.assertEqual(changed, "docs/leaderboard.md")
            self.assertEqual((repo / "docs" / "experiments.md").read_text(), "# Manual history\n")
            bot = [{"number": 1, "headRefName": sync_leaderboard.BRANCH,
                    "files": [{"path": sync_leaderboard.FILE}]}]
            with patch.object(sync_leaderboard, "_run", side_effect=run), \
                    patch.object(sync_leaderboard, "_pull_requests", return_value=bot):
                again = sync_leaderboard.sync_once(repo, "test/repo", "upstream",
                                                   "/bin/true", SimpleNamespace(version="v1"), store)
            self.assertIn("Unchanged", again)
            self.assertEqual(len(created), 1)

    def test_manual_leaderboard_pr_blocks_automatic_pr(self):
        manual = [{"number": 8, "headRefName": "docs/mcp-live-records",
                   "files": [{"path": sync_leaderboard.FILE}]}]
        with patch.object(sync_leaderboard, "_pull_requests", return_value=manual), \
                patch.object(sync_leaderboard, "_run") as run:
            result = sync_leaderboard.sync_once("/unused", "test/repo", "upstream",
                                                "/bin/true", SimpleNamespace(version="v1"), None)
        self.assertIn("Skipped", result)
        run.assert_not_called()
