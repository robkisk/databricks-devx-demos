#!/bin/sh
# clean_room.sh: a shell for recording the demo, with its own HOME, so Omnigent's login and default
# server (~/.omnigent) and the Databricks CLI's login (~/.databrickscfg) stay out of your real home.
#
# usage: scripts/clean_room.sh              an interactive bash with the prompt "$ "
#        scripts/clean_room.sh <command>    run one command inside it
#
# DEMO_HOME (default: .demo-home next to this folder's README) becomes HOME. Tools you install inside
# it with `uv tool install` land in $DEMO_HOME/.local/bin, which goes first on the PATH. Variables
# that would point an agent at another model gateway (ANTHROPIC_*, CLAUDE_*, OPENAI_*, CODEX_*,
# UG_*, OMNIGENT_*) are dropped. `rm -rf .demo-home` resets all of it.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
demo_home=${DEMO_HOME:-$here/.demo-home}
mkdir -p "$demo_home"
for v in $(env | grep -E -o '^(ANTHROPIC|CLAUDE|OPENAI|CODEX|UG|OMNIGENT)[A-Za-z0-9_]*=' | tr -d '='); do
  unset "$v"
done
export HOME="$demo_home"
export PATH="$demo_home/.local/bin:$PATH"
cd "$here"
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
export PS1='$ ' BASH_SILENCE_DEPRECATION_WARNING=1
exec bash --noprofile --norc -i
