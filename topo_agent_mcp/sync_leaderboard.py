# SPDX-License-Identifier: AGPL-3.0-or-later
"""Publish only the current leaderboard snapshot through a reviewable PR."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from topo_agent_mcp.benchmark import Benchmark
from topo_agent_mcp.export import _leaderboard
from topo_agent_mcp.store import Store


BRANCH = "bot/leaderboard-snapshot"
FILE = "docs/leaderboard.md"


def _run(args, cwd=None):
    """Run a command and return its standard output, failing on errors."""
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def _pull_requests(repo_slug):
    """Read open PRs so a manual leaderboard PR is never duplicated."""
    return json.loads(_run(["gh", "pr", "list", "--repo", repo_slug, "--state", "open",
                            "--json", "number,headRefName,files"]))


def sync_once(repo, repo_slug, remote, test_python, benchmark, store):
    """Refresh one scoreboard PR when the server has newer results."""
    repo = Path(repo).resolve()
    prs = _pull_requests(repo_slug)
    bot = next((pr for pr in prs if pr["headRefName"] == BRANCH), None)
    if any(pr["headRefName"] != BRANCH and
           any(item["path"] == FILE for item in pr["files"]) for pr in prs):
        return "Skipped: another open PR updates the leaderboard"
    _run(["git", "-C", str(repo), "fetch", remote])
    snapshot = _leaderboard(benchmark, store.runs(benchmark.version))
    if bot is not None:
        published = _run(["git", "-C", str(repo), "show",
                          f"{remote}/{BRANCH}:{FILE}"])
        if published == snapshot.strip():
            return f"Unchanged: PR #{bot['number']} already has the current leaderboard"
    with tempfile.TemporaryDirectory(prefix="topo-leaderboard-") as directory:
        checkout = Path(directory) / "checkout"
        _run(["git", "-C", str(repo), "worktree", "add", "--detach", str(checkout),
              f"{remote}/main"])
        try:
            target = checkout / FILE
            if target.read_text(encoding="utf-8") == snapshot:
                return "Unchanged: main already has the current leaderboard"
            target.write_text(snapshot, encoding="utf-8")
            changed = _run(["git", "diff", "--name-only"], cwd=checkout).splitlines()
            if changed != [FILE]:
                raise RuntimeError(f"Refusing to publish unexpected files: {changed}")
            _run([test_python, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                 cwd=checkout)
            _run([test_python, "-m", "pyflakes", "topo_agent", "tests"], cwd=checkout)
            _run(["git", "add", "--", FILE], cwd=checkout)
            _run(["git", "-c", "user.name=Topo Leaderboard Bot",
                  "-c", "user.email=topo-leaderboard@users.noreply.github.com",
                  "commit", "-m", "Update real-route leaderboard snapshot"], cwd=checkout)
            ref = f"refs/heads/{BRANCH}"
            previous = _run(["git", "ls-remote", remote, ref], cwd=checkout).split()
            lease = f"--force-with-lease={ref}:{previous[0]}" if previous else "--force-with-lease"
            _run(["git", "push", lease, remote, f"HEAD:{ref}"], cwd=checkout)
            if bot is None:
                body = ("Automated snapshot of complete 68-route runs from the team MCP server.\n\n"
                        "Only `docs/leaderboard.md` is changed. Times are submitter-reported; "
                        "the development set is not an independent final test.\n\n"
                        "Checks: full offline unittest suite and pyflakes passed.\n")
                body_file = Path(directory) / "pr-body.md"
                body_file.write_text(body, encoding="utf-8")
                _run(["gh", "pr", "create", "--repo", repo_slug, "--base", "main",
                      "--head", BRANCH, "--title", "Update real-route leaderboard snapshot",
                      "--body-file", str(body_file)])
                return "Created leaderboard-only PR"
            return f"Updated leaderboard-only PR #{bot['number']}"
        finally:
            _run(["git", "-C", str(repo), "worktree", "remove", "--force", str(checkout)])


def main(argv=None):
    """Run one locked sync cycle from a timer or manually."""
    parser = argparse.ArgumentParser(description="Sync the leaderboard into one PR")
    parser.add_argument("--repo", required=True, help="Local topo-agent checkout")
    parser.add_argument("--repo-slug", default="Mirai-Climbing/topo-agent")
    parser.add_argument("--remote", default="upstream")
    parser.add_argument("--test-python", required=True)
    args = parser.parse_args(argv)
    lock = Path(os.environ.get("TOPO_MCP_OUT", "out")) / "leaderboard-sync.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        benchmark = Benchmark(os.environ.get("TOPO_AGENT_ROOT", args.repo),
                              os.environ.get("TOPO_MCP_DATA_DIR"))
        store = Store(os.environ.get("TOPO_MCP_DB", "out/experiments.sqlite3"))
        print(sync_once(args.repo, args.repo_slug, args.remote, args.test_python,
                        benchmark, store))


if __name__ == "__main__":
    sys.exit(main())
