# Video runbook: the store-ops analyst, end to end

A recording plan for a walkthrough of this demo, with chapters, rough timings, and a reset between takes.
Commands come from [README.md](README.md); this file says what to show, what to pre-stage, and what to
keep off camera. Total run time is about 15 minutes before editing, and 8 to 10 after cutting the waits.

## Before the first take

Do these once, off camera:

1. **Deploy the data** (README step 1). It takes about a minute, and it's the same on every take, so show
   the bundle's files on camera rather than the deploy itself.
2. **Make the Sandbox a host** (README step 6). It's slow and prints your workspace URL, so pre-stage it
   too. Check that `scripts/sandbox_host.sh status …` shows `host=online` before each session.
3. **Open the clean room** and log in there, so nothing on screen comes from your real home directory:

   ```bash
   scripts/clean_room.sh                   # a bash with HOME=.demo-home and the prompt "$ "
   databricks auth login --host "$WORKSPACE_URL" -p demo
   uv tool install "omnigent[databricks] @ git+https://github.com/omnigent-ai/omnigent.git@d04000ef"
   omni login "$WORKSPACE_URL/omnigent"
   export PROFILE=demo CATALOG=<catalog>
   ```

   The OAuth login opens a browser tab that shows your workspace and email; don't record it. The profile
   name `demo` is all the camera sees afterward.
4. **Run the whole demo once** (chapters 2 to 6), then `scripts/reset.sh`. A dry run catches an expired
   Sandbox or a changed MCP tool list before you're recording.

## Checklist before each take

- [ ] Use a fresh demo profile: `demo` in the clean room, never your everyday one.
- [ ] Set a prompt that shows no hostname or user: the clean room's `$ `.
- [ ] Enlarge the font: 18 pt or more, and a terminal about 100 columns wide, so the tables don't wrap.
- [ ] Clear the scrollback (`clear && printf '\033[3J'`, or your terminal's clear-buffer key).
- [ ] Silence notifications: macOS Focus or Do Not Disturb, and quit chat apps.
- [ ] Hide `~/.databrickscfg`, tokens, and the browser's address bar. Never show a PAT.
- [ ] Run `scripts/reset.sh` if a take came before this one, and check its last lines:
      `sessions left: 0` and `agent: removed`.

## Chapters

| # | Chapter | Time | What to show | Recorder |
| --- | --- | --- | --- | --- |
| 1 | What we're building | 1:00 | The post's diagram, then this folder's tree | Screen |
| 2 | The data | 1:30 | `bundle/databricks.yml`, then the four UC functions in Catalog Explorer and the dashboard | Screen |
| 3 | The playbook is a UC skill | 1:30 | `templates/skill/SKILL.md`, then `render.py` and `publish_skill.py` with its four `ok` lines | Terminal |
| 4 | The agent is one file | 2:00 | `build/agent/config.yaml`, `mcp_tools.py`, `test_policy.py`, `omnigent agent add` printing version 1 | Terminal |
| 5 | Run it on the Sandbox | 3:00 | `omni_rest.py hosts` and `session`, `omni attach` in a second pane, then the Pacific and S-007 questions | Terminal, two panes |
| 6 | Genie One and the read-only guard | 2:30 | The Produce trend question, then the `SET` probe and `Denied by policy` | Terminal |
| 7 | Fix the skill, not the agent (optional) | 2:00 | README's "Fix the skill" section: the miss, the one-line fix, the reload | Terminal |
| 8 | Wrap up | 0:30 | `reset.sh`, and where the repo and post live | Terminal |

Timings are for the final cut. Each agent turn takes 30 to 80 seconds; cut the waits but keep a few
seconds of tool calls streaming in `omni attach`, which is the point of chapter 5.

### Notes per chapter

- **Chapter 3.** `render.py` prints only file paths. Open the rendered `SKILL.md` only if you're fine
  showing your catalog name; the template shows the same text with `{{catalog}}`.
- **Chapter 4.** The rendered `config.yaml` holds your workspace host and ID in three URLs. Show
  `templates/agent/config.yaml` instead, or blur those lines. `test_policy.py` downloads omnigent the first
  time; run it once before recording so the take is fast.
- **Chapter 5.** Keep the session ID; you need it for every `ask`. Put `omni attach <session-id>` in a
  second pane before the first question. Check every number against `scripts/expected.py`, including
  totals the agent adds up itself: one verification run summed S-007's units to 9,750 instead of 8,652.
- **Chapter 6.** Genie One's reply ends with an "Explore in Databricks" link that contains your workspace
  host and ID. Blur it, or crop it out. Genie One's run is the slowest (60 to 80 seconds) and its wording
  varies the most; the step on October 21 is the stable part.
- **Chapter 7.** The miss isn't guaranteed: with the counting rule gone, the agent may still count right.
  If it does, say so on camera and show the rule anyway. Record a failure that teaches something rather
  than retaking for a clean run.

## Terminal-only segments

Chapters 3, 4, and 8 are short, scripted, and repeatable, so they suit [VHS](https://github.com/charmbracelet/vhs)
(a `.tape` file you can re-record when a CLI changes). Chapters 5 to 7 are real agent runs; record them
live, or with [asciinema](https://asciinema.org/) for an embeddable cast. Record from inside
`scripts/clean_room.sh` either way, so the casts carry the clean prompt and HOME.

## Reset between takes

```bash
scripts/reset.sh
```

It deletes the sessions that use the agent, removes the agent, deletes the UC skill, and removes `build/`.
After it, chapter 3 starts from nothing: `publish_skill.py` prints `created`, and `omnigent agent add`
prints version 1 again. The data and the Sandbox host stay, since they're pre-staged.

To start over completely (a new clean room, a new host):

```bash
scripts/reset.sh                                                        # inside the clean room
scripts/sandbox_host.sh remove "$SANDBOX" "$PROFILE" "$WORKSPACE_URL"
exit                                                                    # leave the clean room
rm -rf .demo-home                                                       # its logins and the omnigent install
```
