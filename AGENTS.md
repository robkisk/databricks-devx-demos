# terminal-poet demos

Public, runnable demos for posts on terminalpoet.com. One folder per demo, each with a README (exact
commands, verified versions, teardown) and, where there's a video, a RUNBOOK.md.

- **Public information only.** No workspace hosts or IDs, catalog names, emails, profile names, warehouse,
  session, host, or agent IDs, internal tool names, or internal links. Templates use `{{placeholders}}`, and
  `scripts/render.py` fills them into the gitignored `build/`.
- **Every command in a README was run** on the date its verified line states. Change a command, rerun it,
  and update the line.
- **Scripts are standalone uv scripts** (`#!/usr/bin/env -S uv run --script`) with pinned dependencies and
  no imports from outside the demo folder.
- **Name Databricks products by their current names:** UC, DABs, Genie One, Genie Agents, Unity Gateway.
