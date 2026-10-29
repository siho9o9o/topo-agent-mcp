# SPDX-License-Identifier: AGPL-3.0-or-later
"""Export server records to the team's reviewable repository documents."""

import argparse
import os
from pathlib import Path

from topo_agent_mcp.benchmark import Benchmark
from topo_agent_mcp.store import Store


BEGIN = "<!-- topo-agent-mcp:begin -->"
END = "<!-- topo-agent-mcp:end -->"


def export_repo(store, benchmark, repo):
    """Refresh the managed records block and current leaderboard snapshot."""
    repo = Path(repo).resolve()
    if not (repo / "topo_agent" / "eval.py").is_file():
        raise ValueError("--repo must point to a topo-agent checkout")
    docs = repo / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    experiments = docs / "experiments.md"
    existing = experiments.read_text(encoding="utf-8") if experiments.exists() else "# Experiments\n"
    block = _experiment_block(store.experiments(limit=None))
    experiments.write_text(_replace_block(existing, block), encoding="utf-8")
    leaderboard = docs / "leaderboard.md"
    leaderboard.write_text(_leaderboard(benchmark, store.runs(benchmark.version)), encoding="utf-8")
    return experiments, leaderboard


def _replace_block(existing, content):
    managed = f"{BEGIN}\n{content}\n{END}"
    if BEGIN in existing or END in existing:
        if existing.count(BEGIN) != 1 or existing.count(END) != 1:
            raise ValueError("Malformed managed experiment block")
        start = existing.index(BEGIN)
        finish = existing.index(END) + len(END)
        if start >= finish:
            raise ValueError("Malformed managed experiment block")
        return existing[:start] + managed + existing[finish:]
    return existing.rstrip() + "\n\n" + managed + "\n"


def _experiment_block(notes):
    lines = ["## Shared MCP experiment records", "",
             "These entries were exported from the team MCP server. The server database",
             "retains the full record; this section is the repository snapshot.", ""]
    if not notes:
        lines.append("No MCP experiment records have been submitted yet.")
    for note in notes:
        lines.extend([f"### {_plain(note['title'])}", "",
                      f"- Author: {_plain(note['author'])}",
                      f"- Recorded: {note['created_at']}",
                      f"- Commit: `{note['commit_sha'] or 'none'}`",
                      f"- Tags: {', '.join(_plain(tag) for tag in note['tags']) or 'none'}",
                      "", f"> {_plain(note['summary'])}", ""])
    return "\n".join(lines).rstrip()


def _leaderboard(benchmark, runs):
    runs = sorted(runs, key=lambda run: (-run["metrics"]["f1"],
                                         -run["metrics"]["precision"],
                                         run["metrics"]["seconds"], run["created_at"]))
    lines = ["# Real-route leaderboard", "",
             "This is a snapshot exported from the topo-agent MCP server. The eight photos",
             "and 68 annotated routes are a development set, not an independent test set.",
             "Accuracy is recalculated by the server using `topo_agent.eval.match`.",
             "Execution times are reported by submitters and are not independently verified.", "",
             f"Dataset and evaluator version: `{benchmark.version}`", "",
             "| Rank | Author | Method | Commit | F1 | Recall | Precision | Mean seconds | Run ID |",
             "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for rank, run in enumerate(runs, 1):
        m = run["metrics"]
        cells = [str(rank), _cell(run["author"]), _cell(run["method"]),
                 f"`{run['commit_sha']}`", f"{m['f1']:.1%}", f"{m['recall']:.1%}",
                 f"{m['precision']:.1%}", f"{m['seconds']:.1f}", f"`{run['id']}`"]
        lines.append("| " + " | ".join(cells) + " |")
    if not runs:
        lines.extend(["", "No complete benchmark runs have been submitted yet."])
    return "\n".join(lines) + "\n"


def _plain(value):
    return " ".join(str(value).split()).replace("`", "'").replace("<", "&lt;").replace(">", "&gt;")


def _cell(value):
    return _plain(value).replace("|", "\\|")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export MCP records to topo-agent docs")
    parser.add_argument("--repo", required=True, help="topo-agent checkout to update")
    args = parser.parse_args(argv)
    topo_root = os.environ.get("TOPO_AGENT_ROOT", args.repo)
    data = os.environ.get("TOPO_MCP_DATA_DIR")
    database = os.environ.get("TOPO_MCP_DB", "out/experiments.sqlite3")
    files = export_repo(Store(database), Benchmark(topo_root, data), args.repo)
    for path in files:
        print(path)


if __name__ == "__main__":
    main()
