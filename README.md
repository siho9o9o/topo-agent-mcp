# Topo-agent experiment server

A separate MCP server and read-only web leaderboard for the `topo-agent` team. Teammates
connect their agents to one Streamable HTTP endpoint, share experiment notes, and submit
predictions for the same real-photo development benchmark. The server keeps records in
SQLite and calculates accuracy with the `topo-agent` evaluator. No login is required;
authors enter their names when they submit.

## Connect your agent

Use the same MCP URL in every client. First, set the current test endpoint in the
terminal where you will run Codex, Claude Code, or Muse Code:

```bash
export TOPO_EXPERIMENTS_MCP_URL="https://countries-tied-seriously-investing.trycloudflare.com/mcp"
```

This is a temporary Cloudflare tunnel. It stops working when the server or tunnel stops,
but restarting only the application server leaves the tunnel URL unchanged. If the
tunnel restarts, replace the URL in the line above with its new address and reconnect
your client. Replace it with the team's stable URL when one is deployed. No API key or
sign-in is needed for this server.

### Codex CLI

Run this in a terminal:

```bash
codex mcp add topo-experiments --url "$TOPO_EXPERIMENTS_MCP_URL"
codex mcp list
```

Start or restart Codex, then use `/mcp` in its terminal UI to check that
`topo-experiments` is available. Ask the agent to call `get_rules` and `get_benchmark`.
To inspect the saved entry, run `codex mcp get topo-experiments`. If the tunnel URL
changes, remove the old entry with `codex mcp remove topo-experiments` and add the new
URL. See the [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

### Claude Code

Run this in a terminal:

```bash
claude mcp add --transport http topo-experiments "$TOPO_EXPERIMENTS_MCP_URL"
claude mcp list
```

Open or restart Claude Code and use `/mcp` to check the connection. Ask it to call
`get_rules` and `get_benchmark`. The default MCP scope is local to the project where
you run the command; use `--scope user` if you want the server in every Claude Code
project. If the URL changes, use `claude mcp remove topo-experiments` and add it again.
See the [official Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

### Muse Code

Muse Code reads MCP servers from `~/.config/muse/settings.json` (or
`$XDG_CONFIG_HOME/muse/settings.json`). Add the `topo-experiments` entry to the existing
`mcpServers` object. If the file does not exist, create it with this content:

```json
{
  "schema_version": 1,
  "mcpServers": {
    "topo-experiments": {
      "type": "streamable-http",
      "url": "${TOPO_EXPERIMENTS_MCP_URL}",
      "required": false
    }
  }
}
```

Keep any other settings and servers already in the file. Muse expands the environment
variable in `url`, so start it from the terminal where you exported
`TOPO_EXPERIMENTS_MCP_URL`. Alternatively, replace `${TOPO_EXPERIMENTS_MCP_URL}` in the
JSON with the current URL. `required: false` lets Muse start even if the temporary
tunnel is down. Start a new `muse` process after editing the file and run `/mcp` in Muse
to see the connection and tools. For example, the
`get_rules` tool appears as `mcp__topo_experiments__get_rules`. Muse's `muse mcp login`
command is not needed because this server has no authentication. See the
[Muse Code MCP server documentation](https://meta-models.github.io/muse-code-sdk/next/guides/extend/mcp-servers/).

After connecting any client, ask your agent: “Call `get_rules`, then `get_benchmark`,
and summarize the current leaderboard.” To obtain the photos, ask it to call
`get_dataset_download` and download the returned ZIP URL to your machine.

## Give your agent project rules

Connecting MCP exposes tools; it does not tell a coding agent when to use them or how
to work in `topo-agent`. Use the existing
[`topo-agent/AGENTS.md`](https://github.com/Mirai-Climbing/topo-agent/blob/main/AGENTS.md)
as the source for project rules. In particular, it requires English repository content,
feature branches on the upstream repository, no push to `main`, user approval before
opening a PR, the full offline unit suite and `pyflakes` before a PR, benchmark results
for behavior changes, and careful handling of API keys and real photos.

**Codex and Muse Code users:** keep the repository's `AGENTS.md`. Add the following
section to it for the shared experiment workflow. Do not replace its existing Git,
testing, privacy, or evaluation rules:

```markdown
## Shared experiment MCP

- Connect the `topo-experiments` MCP server before doing experiment work.
- Before an experiment, call `get_rules`, `search_experiments`, and `get_leaderboard`.
- Call `get_benchmark` to obtain the current dataset version and all required case IDs.
- Use `get_dataset_download` when you need the eight-photo dataset; verify its SHA-256.
- After every experiment, call `submit_experiment` with your name, code commit, settings,
  result, and what you learned. Also update `docs/experiments.md` and
  `docs/learnings.md` as required by this repository's AGENTS.md.
- For a benchmark run, call `submit_run` with all annotated routes, including failures.
  Do not submit a partial run as a leaderboard result.
- Keep predictions and traces under `out/`; never send API keys or personal data to MCP.
```

**Claude Code users:** put instructions in `CLAUDE.md` at the root of your `topo-agent`
checkout. The first line imports the existing `AGENTS.md`, so Claude receives the full
project rules, including Git push, PR, unit test, and `pyflakes` requirements. Add the
MCP workflow there too:

```markdown
@AGENTS.md

## Claude Code and shared experiments

- Follow the imported AGENTS.md: work on upstream feature branches, never push to
  `main`, and ask the user before opening a PR.
- Before a PR, run the complete unit test suite and `pyflakes`. Include the required
  benchmark results for behavior changes. Do not weaken tests or change evaluation
  scoring rules without the user's approval.
- Before an experiment, call the `topo-experiments` MCP tools `get_rules`,
  `search_experiments`, `get_leaderboard`, and `get_benchmark`.
- Use `get_dataset_download` to get the dataset URL and verify the ZIP's SHA-256.
- After an experiment, call `submit_experiment` with your name, commit, settings,
  result, and learning. Update `docs/experiments.md` and `docs/learnings.md` too.
- Submit complete 68-route benchmark predictions with `submit_run`, including failures.
- Keep traces under `out/`; never send API keys or personal data to MCP.
```

Claude Code supports the `@AGENTS.md` import in `CLAUDE.md`; see its
[project memory documentation](https://code.claude.com/docs/en/memory).

## What it provides

| MCP tool | Purpose |
| --- | --- |
| `get_rules` | Read team experiment rules. |
| `get_benchmark` | Get the dataset/evaluator version and all required case IDs. |
| `get_dataset_download` | Get a separate ZIP download URL for the eight photos and annotations. |
| `search_experiments` | Find earlier notes by text or tag. |
| `submit_experiment` | Append a named experiment note. |
| `submit_run` | Submit all case predictions; the server scores and records them. New frontier records also create an experiment note. |
| `get_leaderboard` | Read runs ranked by F1, precision, and mean time. |
| `get_run` | Inspect one run's case-level results. |

The website at `/` shows the leaderboard and notes. It has no dataset download link.
Use `get_dataset_download` through MCP to obtain the ZIP URL. The ZIP contains
`annotations.json`, the eight original JPEGs, `SOURCES.md`, and `DATASET_VERSION.txt`.
The tool also returns the ZIP's SHA-256 and size so clients can check the download.
The source dataset and attribution are described in the ZIP's `SOURCES.md` (CC BY-SA 4.0).

## Run the server

Python 3.11 or newer is required. Keep this project next to a checkout of `topo-agent`
with `topo_agent/eval.py`. Provide a local copy of the licensed `real_routes` dataset
directory containing `annotations.json`, `SOURCES.md`, and `images/`. The server's
local data copy lives under the ignored `out/real_routes/` directory in this project.
No files in `topo-agent` are modified by this server.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
TOPO_AGENT_ROOT=/path/to/topo-agent \
TOPO_MCP_DATA_DIR=/path/to/real_routes \
.venv/bin/topo-mcp
```

The local MCP endpoint is `http://127.0.0.1:8766/mcp`; the site is
`http://127.0.0.1:8766/`. To serve teammates, put this process behind a stable public
HTTPS address and set:

```bash
TOPO_AGENT_ROOT=/path/to/topo-agent \
TOPO_MCP_DATA_DIR=/path/to/real_routes \
TOPO_MCP_PUBLIC_URL=https://your-host.example \
TOPO_MCP_ALLOWED_HOST=your-host.example \
.venv/bin/topo-mcp
```

The application listens on `127.0.0.1:8766` by default for a reverse proxy or tunnel.
`TOPO_MCP_HOST` and `TOPO_MCP_PORT` change its bind address. `TOPO_MCP_DB` changes the
SQLite path (default `out/experiments.sqlite3`); back up that file for durable history.
`TOPO_MCP_OUT` changes where generated ZIPs are cached (default `out/`).

## Submit a run

Call `get_benchmark` first. `submit_run` takes `author`, `method`, a Git `commit_sha`,
the exact `dataset_version`, optional `notes`, and `rows`. Each row has `case_id`,
`seconds`, `holds`, and optional `error`. Include **every** case ID, including failures.
Use `holds: []` for a failure. Hold coordinates are normalized to `[0, 1]` and each hold
needs `x`, `y`, and either a normalized `r` or polygon `points`.

```json
{
  "case_id": "bh0003_r0",
  "seconds": 1.2,
  "holds": [{"x": 0.42, "y": 0.02, "r": 0.01}],
  "error": ""
}
```

The server rejects missing/duplicate cases and mismatched dataset versions. It uses
the configured checkout's `topo_agent.eval.match` and `summary` functions without
changing their scoring rules. Its version hash includes the manifest, JPEGs, and
evaluator source. The server recalculates hits, recall, precision, and F1 from submitted
predictions. **Execution time is reported by the submitter**, because the server does
not execute teammates' code. The leaderboard labels this limitation. To compare speed,
run on comparable hardware and record the environment in `notes`.

A new run is a frontier record when no earlier run has both equal or better F1 and equal
or lower mean time. The server then creates an experiment note automatically. All runs
remain available even when a later run supersedes a record.

The eight photos were used during development. This leaderboard tracks improvement on
that development set; it is not an independent test of generalization.

The current shared matcher counts 583 of 587 holds when the submitted polygons are
identical to the annotation polygons. Its center-inside matching rule misses four
irregular cases. This server deliberately preserves the shared scoring contract;
interpret scores with that limitation in mind.

## Tests

Tests use the real `samples/real_routes` fixture and never call model APIs:

```bash
TOPO_AGENT_ROOT=/path/to/topo-agent \
TOPO_MCP_DATA_DIR=/path/to/real_routes \
.venv/bin/python -m unittest discover -s tests -v
```
