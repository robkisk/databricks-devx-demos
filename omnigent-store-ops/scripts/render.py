#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["databricks-sdk==0.170.0"]
# ///
"""Fill in the skill and agent templates for your workspace, into build/.

usage: scripts/render.py -p <profile> --catalog <catalog> [--schema retail_stockout]
       [--skills-schema agent_skills] [--agent-name store-ops-analyst] [--agent-profile DEFAULT]
       [--without-counting-rule]

It reads the workspace host and ID from <profile>, and writes:
  build/skill/store-ops-analyst/SKILL.md   the playbook to publish as a UC skill
  build/agent/config.yaml                  the Omnigent agent to install

--agent-profile is the Databricks CLI profile the agent uses on its host. Keep DEFAULT for a
Databricks Sandbox host; on a laptop host, pass your own profile.
--without-counting-rule leaves out the playbook rule that makes the agent count draft lines with
replenishment_plan, so you can show the miss and the fix (see RUNBOOK.md).
"""
import argparse
import pathlib
import re
import sys

from databricks.sdk import WorkspaceClient

COUNTING_RULE = "- A draft order holds only the HIGH and MEDIUM lines that `replenishment_plan` returns."

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-p", "--profile", required=True, help="your Databricks CLI profile for the workspace")
parser.add_argument("--catalog", required=True)
parser.add_argument("--schema", default="retail_stockout", help="the bundle's data schema")
parser.add_argument("--skills-schema", default="agent_skills", help="the schema that holds the UC skill")
parser.add_argument("--agent-name", default="store-ops-analyst")
parser.add_argument("--agent-profile", default="DEFAULT")
parser.add_argument("--without-counting-rule", action="store_true")
args = parser.parse_args()

w = WorkspaceClient(profile=args.profile)
values = {
    "catalog": args.catalog,
    "schema": args.schema,
    "skills_schema": args.skills_schema,
    "agent_name": args.agent_name,
    "profile": args.agent_profile,
    "workspace_host": re.sub(r"^https?://", "", w.config.host).rstrip("/"),
    "workspace_id": str(w.get_workspace_id()),
}

here = pathlib.Path(__file__).resolve().parent.parent
outputs = {
    "templates/skill/SKILL.md": "build/skill/store-ops-analyst/SKILL.md",
    "templates/agent/config.yaml": "build/agent/config.yaml",
}
for src, dst in outputs.items():
    text = (here / src).read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    if leftover := re.findall(r"\{\{\w+\}\}", text):
        sys.exit(f"{src}: unfilled placeholders {sorted(set(leftover))}")
    if src.endswith("SKILL.md") and args.without_counting_rule:
        lines = [line for line in text.splitlines(keepends=True) if not line.startswith(COUNTING_RULE)]
        if len(lines) == len(text.splitlines()):
            sys.exit("the counting rule wasn't found in the skill template")
        text = "".join(lines)
    out = here / dst
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print("wrote", out.relative_to(here))
