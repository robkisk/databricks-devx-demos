# Databricks DevX demos

Runnable demos of Databricks developer tooling: agents and harnesses, CLIs, and the platform pieces behind
them. Each demo lives in its own folder, with the exact commands, the versions it was verified with, and a way
to tear it all down. Most have a companion post on [terminalpoet.com](https://terminalpoet.com).

This is a personal project, not an official Databricks repository.

| Demo | Post | What it shows |
| --- | --- | --- |
| [omnigent-store-ops](omnigent-store-ops/) | [Omnigent on a Databricks Sandbox: a UC skill, Genie One and a build from main](https://terminalpoet.com/posts/omnigent/) | An agent packaged as one Omnigent folder, whose playbook is a UC skill and whose tools are Genie One and read-only SQL, running on a Databricks Sandbox host |

All data here is synthetic. Everything runs in your own workspace with your own credentials: no file in this
repo holds a host, an ID, or a key.

---

## omnigent-store-ops

A store-operations analyst for a made-up grocery chain. You ask it which stores are about to run out of
stock, and it answers with exact numbers from UC functions, open-ended trends from Genie One, and a draft
replenishment order that it flags for a buyer. It never writes data, and the platform enforces that, not
just the prompt.

> Verified November 24, 2026 with omnigent 0.24.0.dev0 built from `main` at `d04000ef` (laptop and Sandbox
> host), Omnigent on Databricks (Beta, server 0.23.0.dev0), Databricks CLI v1.27.0, uv 0.13.5,
> databricks-sdk 0.170.0, mcp 2.3.0, and Claude Opus 5.5 through Unity Gateway.

**Contents:** [What runs where](#what-runs-where) ·
[One question, end to end](#one-question-end-to-end) · [The data](#the-data) ·
[Read-only, enforced twice](#read-only-enforced-twice) · [Run it](#run-it) ·
[What a run looks like](#what-a-run-looks-like) · [Reset and teardown](#reset-and-teardown) ·
[What's in the folder](#whats-in-the-folder) · [Things that trip people up](#things-that-trip-people-up)

### What runs where

<img alt="Your laptop installs the agent on Omnigent on Databricks and follows its sessions. The server reaches a Databricks Sandbox host over a tunnel, and the agent on that host calls a UC skill, Genie One MCP, Databricks SQL MCP, and Claude through Unity Gateway." src="omnigent-store-ops/diagrams/architecture-light.png" width="720">

The agent is one `config.yaml` and no code. Everything else comes from the workspace:

| Piece | Status | Its job |
| --- | --- | --- |
| [UC skill](https://docs.databricks.com/aws/en/agents/uc-skills/) | Beta | The playbook: where the data is, which tool to use, the rules, the answer format |
| [Genie One MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp) | GA | Open questions about trends and causes, answered with Genie's own SQL |
| [Databricks SQL MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/databricks-sql) | Beta | Exact numbers, rankings, and draft orders from the UC functions |
| Claude Opus 5.5 through [Unity Gateway](https://docs.databricks.com/aws/en/unity-gateway/) | GA (Unity Gateway) | The model |
| [Omnigent on Databricks](https://docs.databricks.com/aws/en/omnigent/) | Beta | Sessions, the agent catalog, and policies, run by Databricks |
| [Databricks Sandbox](https://docs.databricks.com/aws/en/compute/serverless/sandbox) | Beta | The machine the agent runs on, with your own credential as its `DEFAULT` profile |

[Omnigent](https://omnigent.ai/) is an open source meta-harness: it sits above coding agents such as Claude
Code and Codex and gives them one session model, one policy layer, and one set of interfaces. This demo uses
its [custom agent](https://omnigent.ai/docs/use/custom-agents) format on the `claude-sdk` harness.

### One question, end to end

<img alt="A sequence diagram. You send the question to Omnigent on Databricks, which runs the turn on the Sandbox host. The agent loads its playbook from the UC skills MCP, sends a SELECT on stores_at_risk through the CEL guardrail, which allows it, runs it on the Databricks SQL MCP, then calls replenishment_plan for each store, and returns the answer with every tool call. omni attach streams the transcript live." src="omnigent-store-ops/diagrams/one-turn-light.png" width="820">

The agent loads its playbook by full name before its first answer, every session. Fix the playbook in UC and
the next load picks it up, with no reinstall. The post's [Fix the skill, not the agent](https://terminalpoet.com/posts/omnigent/#fix-the-skill-not-the-agent)
section shows that happening in a live session, and the folder README shows you
[how to reproduce it](omnigent-store-ops/README.md#fix-the-skill-not-the-agent-optional).

### The data

<img alt="databricks bundle deploy runs a job that creates eight tables in the retail_stockout schema. The tables and two scalar UC functions feed the v_stockout_risk view, which feeds the two table functions the agent calls through the Databricks SQL MCP. Genie One and the Genie Agent read the tables, and the AI/BI dashboard reads the view." src="omnigent-store-ops/diagrams/data-model-light.png" width="860">

One [DABs](https://docs.databricks.com/aws/en/dev-tools/bundles/) bundle builds everything in
`<catalog>.retail_stockout`, generated in SQL with no external files:

- **32 stores** in four regions (Pacific, Mountain, Central, Southeast), **120 SKUs** in eight categories,
  **60 days** of sales.
- **The story:** two SKUs per category went on promo 10 days before the as-of date and sell 1.8 times faster,
  and some come from suppliers with lead times over a week. A store-SKU is HIGH risk when its days of cover
  run out before a new order could arrive.
- **Deterministic and pinned:** the noise comes from `xxhash64`, and every date hangs off
  `demo_config.as_of_date`, which the bundle pins to **2026-10-30**. Your numbers match the ones below.
- **The build checks itself:** the job's last task fails the build if the data stops telling that story (the
  HIGH-risk share drifts out of 2 to 15%, say, or nothing needs a buyer).

| Object | Kind | Use |
| --- | --- | --- |
| `stores_at_risk(region, category, n)` | Table function | Stores ranked by HIGH-risk SKUs, with each one's draft order cost |
| `replenishment_plan(store_id)` | Table function | One store's draft order: HIGH and MEDIUM lines, `needs_escalation` on each |
| `v_stockout_risk` | View | One row per store and SKU: 14-day demand, days of cover, risk, reorder units, cost |
| `stockout_risk_level(days_of_cover, lead_time_days)` | Scalar function | HIGH, MEDIUM, or LOW, for what-ifs |
| `reorder_qty(on_hand, on_order, avg_daily_units, lead_time_days, review_days, safety_days, case_pack)` | Scalar function | Units to order, rounded up to whole cases |

### Read-only, enforced twice

<img alt="A request that would write data meets layer 1, the playbook's read-only rule, where the agent refuses a CREATE TABLE. A tool call it does make meets layer 2, the CEL guardrail in Omnigent, which denies SET and EXPLAIN WITH INSERT before they reach the warehouse and allows one read statement through to the Databricks SQL MCP." src="omnigent-store-ops/diagrams/read-only-light.png" width="860">

The playbook tells the agent it's read-only, and the agent follows it. A prompt is not a control, though, so
the agent also carries a [CEL](https://cel.dev/) policy that Omnigent checks before every tool call:

```yaml
guardrails:
  policies:
    sql_reads_only:
      type: function
      function:
        path: omnigent.policies.builtins.cel.cel_policy
        arguments:
          expression: >-
            event.type == "tool_call" && event.data.name.endsWith("execute_sql") &&
            (!has(event.data.arguments.query) || type(event.data.arguments.query) != string ||
             !event.data.arguments.query.matches("^\\s*(?i:select|with|show|describe|explain)\\b") ||
             event.data.arguments.query.matches(";\\s*\\S") ||
             event.data.arguments.query.matches("(?i)\\b(insert|update|delete|merge|create|drop|alter|truncate|grant|revoke|copy|set|use|call|optimize|vacuum|refresh|msck)\\b"))
            ? {"result": "DENY"} : null
          reason: This agent runs read-only SQL. Send one SELECT, WITH, SHOW, DESCRIBE, or EXPLAIN statement.
```

What each layer caught, in the post's run (November 23) and this repo's verification runs (November 24):

| The request | Layer 1: the playbook | Layer 2: the guardrail |
| --- | --- | --- |
| `CREATE TABLE …` | The agent refused and suggested a harmless probe instead | Not reached |
| `WITH x AS (SELECT 1) INSERT INTO …` | The agent refused | Not reached |
| `SET spark.sql.ansi.enabled = true` | Allowed: `SET` isn't on the playbook's list | `Denied by policy`, with no statement ID |
| `EXPLAIN WITH … INSERT INTO …` | Allowed: `EXPLAIN` doesn't write | `Denied by policy` |
| `SELECT * FROM stores_at_risk('Pacific', NULL, 3)` | Allowed | Allowed, and it ran |

`scripts/test_policy.py` runs the same expression against 12 tool calls offline, with omnigent's own handler.

### Run it

<img alt="Seven steps on your laptop and what each leaves behind: bundle deploy creates the data schema; render.py writes build/; the MCP and policy checks change nothing; publish_skill.py creates the UC skill; omnigent agent add installs the agent at version 1; sandbox_host.sh sets up the Sandbox host; omni_rest.py creates a session and gets answers. reset.sh removes the sessions, agent, skill, and build/, and keeps the data and host." src="omnigent-store-ops/diagrams/setup-light.png" width="620">

**You need:**

- A workspace where an admin has turned on three previews: Omnigent, Databricks Sandbox, and Unity Gateway
  skills in Genie. An account admin also turns on Enhanced Unity Gateway, which the SQL MCP needs.
- A UC catalog where you can create schemas, on real managed storage, and a SQL warehouse (the bundle looks
  up `Serverless Starter Warehouse`).
- A [Databricks Sandbox](https://docs.databricks.com/aws/en/compute/serverless/sandbox) (`databricks sandbox
  --help` lists the first steps).
- On your laptop: the [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/) v1.27.0 or later,
  logged in with OAuth, and [uv](https://docs.astral.sh/uv/). Every script is a uv script with pinned
  dependencies, so there's nothing to `pip install`.

**The short version** (the [folder README](omnigent-store-ops/README.md) explains every step and shows its
output):

```bash
git clone https://github.com/robkisk/databricks-devx-demos && cd databricks-devx-demos/omnigent-store-ops
export PROFILE=<your-cli-profile> CATALOG=<your-catalog>
export SANDBOX=<your-sandbox-name> WORKSPACE_URL=https://<workspace-host>

# 1. The data, then the answers the agent should give
(cd bundle && databricks bundle deploy -p "$PROFILE" --var catalog="$CATALOG")
scripts/expected.py -p "$PROFILE" --catalog "$CATALOG"

# 2-4. The playbook and the agent for your workspace; check them; publish the playbook
scripts/render.py -p "$PROFILE" --catalog "$CATALOG"
scripts/mcp_tools.py -p "$PROFILE" --catalog "$CATALOG"
scripts/test_policy.py
scripts/publish_skill.py -p "$PROFILE" --catalog "$CATALOG"

# 5. Omnigent on the laptop, and the agent
uv tool install "omnigent[databricks] @ git+https://github.com/omnigent-ai/omnigent.git@d04000ef"
omni login "$WORKSPACE_URL/omnigent"
omnigent agent add ./build/agent

# 6. The Sandbox as a host
scripts/sandbox_host.sh setup "$SANDBOX" "$PROFILE" "$WORKSPACE_URL"

# 7. Ask
scripts/omni_rest.py -p "$PROFILE" hosts
scripts/omni_rest.py -p "$PROFILE" session --agent store-ops-analyst --host-id <host-id>
scripts/omni_rest.py -p "$PROFILE" ask <session-id> "Which Pacific stores are most at risk of stock-outs? Top 3."
```

Run `omni attach <session-id>` in a second terminal to watch the tool calls as they happen.

### What a run looks like

This is `omni_rest.py ask` from the verification run, with the catalog name generalized and long tool
arguments cut at 140 characters:

```text
----- user -----
Which Pacific stores are most at risk of stock-outs? Top 3.
  tool: ToolSearch  {"query": "select:mcp__omnigent__uc-skills__load_skill,mcp__omnigent__load_skill,mcp__omnigent__dbsql__execute_sql,mcp__
  tool: uc-skills__load_skill  {"full_name": "<catalog>.agent_skills.store-ops-analyst"}
  tool: dbsql__execute_sql  {"query": "SELECT r.*, c.as_of_date FROM <catalog>.retail_stockout.stores_at_risk('Pacific', NULL, 3) r CROSS JO
  tool: dbsql__execute_sql  {"query": "SELECT 'S-021' s, count_if(needs_escalation) esc, count(*) n FROM <catalog>.retail_stockout.replenish
----- assistant -----
As of 2026-10-30, Pacific #021 has the highest stock-out risk in the Pacific region, followed by Pacific #025
and Pacific #017. Stores are ranked by how many SKUs are HIGH risk, meaning their stock runs out before the
supplier lead time.

| Rank | Store              | HIGH-risk SKUs | MEDIUM-risk SKUs | Worst SKU | Draft order lines | Draft order cost |
|------|--------------------|----------------|------------------|-----------|-------------------|------------------|
| 1    | S-021 Pacific #021 | 17             | 12               | SKU-501   | 29                | $20,211.96       |
| 2    | S-025 Pacific #025 | 12             | 13               | SKU-402   | 25                | $25,637.76       |
| 3    | S-017 Pacific #017 | 8              | 14               | SKU-808   | 22                | $17,129.34       |

These orders are drafts only; nothing has been placed.

Escalations: All three stores need a buyer. Each store's draft order is over $5,000 (order-total rule), and
some lines have supplier lead times over 7 days (lead-time rule): 10 lines at S-021, 9 at S-025 and 8 at S-017.

Source: `stores_at_risk('Pacific', NULL, 3)` and `replenishment_plan()` for S-021, S-025 and S-017, in
`<catalog>.retail_stockout`.
----- turn took 41s
----- status=idle pending_approvals=0 cost_usd=0.07375138953 last_error=none
```

The four questions in the folder README, and what a right answer says. `scripts/expected.py` prints the
numbers from your own deployment:

| Question | Tools the agent used | A right answer |
| --- | --- | --- |
| "Which Pacific stores are most at risk of stock-outs? Top 3." | `load_skill`, `execute_sql` on `stores_at_risk` and `replenishment_plan` | S-021, S-025, S-017: 17, 12, and 8 HIGH-risk SKUs; 29, 25, and 22 draft lines; $20,211.96, $25,637.76, $17,129.34; 10, 9, and 8 long-lead lines; every store needs a buyer |
| "Draft the replenishment order for store S-007." | `execute_sql` on `replenishment_plan('S-007')` | 29 lines (17 HIGH, 12 MEDIUM), 8,652 units, $28,845.84, a draft that hasn't been placed |
| "How has Produce demand trended over the last 30 days?" | `genie_ask`, `genie_poll_response` | Flat, then a step up on October 21 when the promo starts; +5.2% second half over first |
| "Send `SET spark.sql.ansi.enabled = true` once and report what comes back." | `execute_sql`, denied | `Denied by policy: This agent runs read-only SQL. …` |

Each turn took 30 to 80 seconds, and the four together came to $0.39 in model costs. Agents are
nondeterministic, so the wording changes from run to run. Check the numbers anyway: in one run the agent got
S-007's lines and cost right and still added its units up to 9,750.

### Reset and teardown

```bash
PROFILE="$PROFILE" CATALOG="$CATALOG" scripts/reset.sh                  # back to a clean start
PROFILE="$PROFILE" CATALOG="$CATALOG" DESTROY_DATA=1 scripts/reset.sh   # also bundle destroy
scripts/sandbox_host.sh remove "$SANDBOX" "$PROFILE" "$WORKSPACE_URL"   # uninstall the Sandbox host
```

`reset.sh` deletes every session that uses the agent, removes the agent, deletes the UC skill, and removes
`build/`, then checks that nothing is left. After it, publishing prints `created` again and
`omnigent agent add` prints version 1, which is what makes a recorded take repeatable.

### What's in the folder

```text
omnigent-store-ops/
├── README.md               every step, with its output
├── RUNBOOK.md              the video plan: chapters, timings, pre-recording checklist, reset between takes
├── bundle/                 DABs: databricks.yml, resources/ (schema, job, Genie Agent, dashboard), src/sql/
├── templates/
│   ├── skill/SKILL.md      the playbook, with {{catalog}}-style placeholders
│   └── agent/config.yaml   the Omnigent agent, with the same placeholders
├── scripts/
│   ├── render.py           fills the templates for your workspace, into build/ (gitignored)
│   ├── expected.py         prints the right answers from your deployed data
│   ├── mcp_tools.py        lists what each MCP endpoint offers you, before you trust an allowlist
│   ├── test_policy.py      tests the read-only guardrail offline
│   ├── publish_skill.py    create, upload, finalize, and read back the UC skill (or --delete)
│   ├── sandbox_host.sh     setup, status, stop, or remove the Omnigent host on a Sandbox
│   ├── omni_rest.py        hosts, agents, session, ask, show, sessions, delete
│   ├── clean_room.sh       a shell with its own HOME and a bare prompt, for recording
│   └── reset.sh            back to a clean start
└── diagrams/               the D2 sources for the diagrams on this page
```

### Things that trip people up

- **Check each MCP server's tools yourself.** The Databricks SQL MCP page lists `execute_sql_read_only`; the
  workspace this was verified on offered only `execute_sql` and `poll_sql_result`. `mcp_tools.py` asks.
- **Policies go under `guardrails.policies`.** A top-level `policies:` block is dropped without a warning by
  `omnigent agent add`, and the agent listing shows `"policies": []` either way. Test the behavior.
- **A CEL error counts as no decision, which allows the call.** That's why the expression checks that `query`
  exists and is a string before it reads it.
- **`wrong_replica` on your own host.** The Omnigent server runs several replicas, and requests for a session
  on your host need `X-Databricks-Omnigent-Slice-Key: <host-id>`. `databricks api` can't send custom headers;
  `omni_rest.py` retries with one.
- **`omni setup` changes more than Omnigent.** Picking Databricks there runs Unity Gateway's CLI, which writes
  machine-wide Claude Code and Codex settings through sudo. This agent doesn't need it: its `executor.auth`
  names the profile.
- **Machine-wide Claude Code settings win.** If your laptop's managed settings point `ANTHROPIC_BASE_URL`
  somewhere else, a Claude harness on the laptop goes there. A Sandbox host doesn't carry your laptop's
  settings.

---

I work at Databricks, which publishes Omnigent as an open source project. Views here are my own.

## License

[Apache-2.0](LICENSE)
