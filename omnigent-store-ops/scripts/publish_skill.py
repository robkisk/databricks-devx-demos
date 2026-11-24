#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["databricks-sdk==0.170.0", "pyyaml==6.0.3"]
# ///
"""Publish a skill folder as a UC skill, then read it back. Or delete it.

usage: scripts/publish_skill.py -p <profile> --catalog <catalog> [--schema agent_skills]
       [--skill-dir build/skill/store-ops-analyst] [--delete]

The three steps from the Skills API reference (Beta):
https://docs.databricks.com/aws/en/ai-gateway/skill-reference
  1. create the skill (once; it creates the schema too if it's missing),
  2. upload every file through the Files API to /Skills/<catalog>/<schema>/<skill>/, SKILL.md last,
  3. finalize, which reads SKILL.md and validates its frontmatter.
Running it again uploads and finalizes again: that's how you update the playbook.
"""
import argparse
import io
import pathlib
import re
import sys

import yaml
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.catalog import Skill

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-p", "--profile", required=True)
parser.add_argument("--catalog", required=True)
parser.add_argument("--schema", default="agent_skills")
parser.add_argument("--skill-dir", default=str(pathlib.Path(__file__).resolve().parent.parent / "build/skill/store-ops-analyst"))
parser.add_argument("--delete", action="store_true", help="delete the store-ops-analyst skill instead of publishing")
args = parser.parse_args()

w = WorkspaceClient(profile=args.profile)

if args.delete:  # needs no local copy, so a reset works from any state
    full_name = f"skills/{args.catalog}.{args.schema}.store-ops-analyst"
    try:
        w.ai_gateway.delete_skill(full_name)
        print("deleted", full_name)
    except NotFound:
        print("not found (already deleted):", full_name)
    sys.exit(0)

root = pathlib.Path(args.skill_dir)
skill_md = (root / "SKILL.md").read_text()
front = yaml.safe_load(skill_md.split("---", 2)[1])
skill = front["name"]
if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill):
    sys.exit(f"frontmatter name {skill!r} must be lowercase letters, digits, and hyphens")
if not front.get("description") or len(front["description"].encode()) > 1024:
    sys.exit("frontmatter description must be nonblank and at most 1024 bytes")
full_name = f"skills/{args.catalog}.{args.schema}.{skill}"

try:
    w.schemas.get(f"{args.catalog}.{args.schema}")
except NotFound:
    w.schemas.create(name=args.schema, catalog_name=args.catalog, comment="UC skills for the store-ops analyst demo.")
    print("created schema", f"{args.catalog}.{args.schema}")

try:
    w.ai_gateway.get_skill(full_name)
except NotFound:
    w.ai_gateway.create_skill(
        Skill(comment="Store-ops analyst playbook from github.com/robkisk/terminal-poet-demos (omnigent-store-ops)."),
        parent=f"schemas/{args.catalog}.{args.schema}", skill_id=skill)
    print("created", full_name)

files = sorted((p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store"),
               key=lambda rel: (rel == "SKILL.md", rel))
base = f"/Skills/{args.catalog}/{args.schema}/{skill}"
for rel in files:
    if " " in rel:
        sys.exit(f"no spaces in skill file names: {rel!r}")
    w.files.upload(f"{base}/{rel}", io.BytesIO((root / rel).read_bytes()), overwrite=True)
    print("uploaded", rel)

w.ai_gateway.finalize_skill(full_name)
got = w.ai_gateway.get_skill(full_name)
stored = w.files.download(f"{base}/SKILL.md").contents.read()
checks = {
    "finalize_time is set": got.finalize_time is not None,
    f"bundle_name is {skill}": got.bundle_name == skill,
    "description matches the frontmatter": (got.description or "").strip() == front["description"].strip(),
    "stored SKILL.md matches the local copy byte for byte": stored == (root / "SKILL.md").read_bytes(),
}
for label, ok in checks.items():
    print("ok  " if ok else "FAIL", label)
if not all(checks.values()):
    sys.exit(1)
print("published", full_name.removeprefix("skills/"))
