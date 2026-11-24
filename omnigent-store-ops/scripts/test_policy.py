#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["omnigent @ git+https://github.com/omnigent-ai/omnigent.git@d04000ef", "pyyaml==6.0.3"]
# ///
"""Check the agent's read-only SQL policy offline, with omnigent's own cel_policy handler.

usage: scripts/test_policy.py [build/agent/config.yaml]

Expect ok on all twelve: reads, including columns named like keywords, and the Genie call pass (None);
SET, DROP, CREATE, a stacked statement, WITH ... INSERT, and an execute_sql call without a string
`query` are denied.
"""
import pathlib
import sys

import yaml
from omnigent.policies.builtins.cel import cel_policy

path = sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "build/agent/config.yaml"
spec = yaml.safe_load(open(path))
policy = cel_policy(**spec["guardrails"]["policies"]["sql_reads_only"]["function"]["arguments"])

SQL = "dbsql__execute_sql"
cases = {  # label: (tool, arguments, expected verdict)
    "select": (SQL, {"query": "SELECT * FROM c.s.stores_at_risk('Pacific', NULL, 3)"}, None),
    "with": (SQL, {"query": "  with t AS (SELECT 1) SELECT * FROM t"}, None),
    "select;": (SQL, {"query": "SELECT 1;"}, None),
    "set": (SQL, {"query": "SET spark.sql.ansi.enabled = true"}, "DENY"),
    "drop": (SQL, {"query": "DROP TABLE c.s.demo_config"}, "DENY"),
    "stacked": (SQL, {"query": "SELECT 1; DROP TABLE c.s.demo_config"}, "DENY"),
    "create": (SQL, {"query": "CREATE TABLE c.s.x (a INT)"}, "DENY"),
    "with+ins": (SQL, {"query": "WITH x AS (SELECT 1) INSERT INTO c.s.t SELECT * FROM x"}, "DENY"),
    "columns": (SQL, {"query": "SELECT updated_at, created_by, reset_count FROM c.s.t"}, None),
    "no query": (SQL, {"statement": "DROP TABLE c.s.demo_config"}, "DENY"),
    "not str": (SQL, {"query": 5}, "DENY"),
    "genie": ("genie__genie_ask", {"question": "DROP everything"}, None),
}
failed = 0
for label, (tool, arguments, want) in cases.items():
    got = policy({"type": "tool_call", "target": tool, "data": {"name": tool, "arguments": arguments}})
    verdict = (got or {}).get("result") if isinstance(got, dict) else got
    ok = verdict == want
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label:8} -> {got}")
sys.exit(1 if failed else 0)
