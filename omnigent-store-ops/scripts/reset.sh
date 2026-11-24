#!/bin/sh
# reset.sh: put the demo back to a clean start, so a take can be redone.
#
# usage: PROFILE=<profile> CATALOG=<catalog> scripts/reset.sh
#
# Undoes, in order:
#   1. every Omnigent session that uses the agent (REST DELETE),
#   2. the installed agent (`omnigent agent remove`, so the next `agent add` prints version 1),
#   3. the UC skill (the next publish creates it again),
#   4. the rendered build/ folder.
# It keeps the data (the agent only reads it) and the Sandbox host. To drop those too:
#   DESTROY_DATA=1 also runs `databricks bundle destroy` for the data schema,
#   scripts/sandbox_host.sh remove ... uninstalls the host from the Sandbox.
#
# Optional: SCHEMA (retail_stockout), SKILLS_SCHEMA (agent_skills), AGENT_NAME (store-ops-analyst).
# Run it where `omnigent` is logged in to the workspace's server (inside scripts/clean_room.sh, if
# you recorded there).
set -eu
: "${PROFILE:?set PROFILE to your Databricks CLI profile}"
: "${CATALOG:?set CATALOG}"
SCHEMA=${SCHEMA:-retail_stockout}
SKILLS_SCHEMA=${SKILLS_SCHEMA:-agent_skills}
AGENT_NAME=${AGENT_NAME:-store-ops-analyst}
here=$(cd "$(dirname "$0")" && pwd)

echo "== sessions using $AGENT_NAME"
for id in $("$here/omni_rest.py" -p "$PROFILE" sessions --agent "$AGENT_NAME" | cut -d' ' -f1); do
  "$here/omni_rest.py" -p "$PROFILE" delete "$id"
done

echo "== agent $AGENT_NAME"
if "$here/omni_rest.py" -p "$PROFILE" agents | grep -q " $AGENT_NAME v"; then
  omnigent agent remove -y "$AGENT_NAME"
else
  echo "not installed"
fi

echo "== UC skill"
"$here/publish_skill.py" -p "$PROFILE" --catalog "$CATALOG" --schema "$SKILLS_SCHEMA" --delete

echo "== build/"
rm -rf "$here/../build"
echo "removed build/"

if [ "${DESTROY_DATA:-0}" = 1 ]; then
  echo "== data schema $CATALOG.$SCHEMA"
  cd "$here/../bundle"
  databricks bundle destroy --auto-approve -p "$PROFILE" --var catalog="$CATALOG" --var schema="$SCHEMA"
fi

echo "== check"
left=$("$here/omni_rest.py" -p "$PROFILE" sessions --agent "$AGENT_NAME" | wc -l | tr -d ' ')
echo "sessions left: $left"
"$here/omni_rest.py" -p "$PROFILE" agents | grep " $AGENT_NAME v" && exit 1 || echo "agent: removed"
