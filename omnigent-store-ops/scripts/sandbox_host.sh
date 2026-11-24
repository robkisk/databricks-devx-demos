#!/bin/sh
# sandbox_host.sh: make a Databricks Sandbox an Omnigent host that runs omnigent built from a pinned
# commit, registered with your workspace's Omnigent server. Or stop it, or remove it.
#
# usage: scripts/sandbox_host.sh <setup|status|stop|remove> <sandbox-name> <profile> <workspace-url>
#   e.g. scripts/sandbox_host.sh setup my-sandbox my-profile https://<workspace-host>
#
# The install goes to ~/.omnigent-main inside the Sandbox and runs by full path, so the Sandbox
# image's own (older) omnigent on the PATH stays as it is. `omni login` uses the Sandbox's DEFAULT
# credential, so no browser opens. `--background` keeps the host up after SSH exits, for as long as
# the Sandbox runs (24 hours at most per start).
set -eu
action=${1:?usage: sandbox_host.sh <setup|status|stop|remove> <sandbox-name> <profile> <workspace-url>}
sandbox=${2:?sandbox name}
profile=${3:?profile}
url=${4:?workspace url}
url=${url%/}
commit=${OMNIGENT_COMMIT:-d04000ef}

env='export UV_TOOL_DIR=$HOME/.omnigent-main/tools UV_TOOL_BIN_DIR=$HOME/.omnigent-main/bin
export OMNIGENT_DATA_DIR=$HOME/.omnigent-main/data OMNIGENT_CONFIG_HOME=$HOME/.omnigent-main/data
omni=$HOME/.omnigent-main/bin/omni'

case "$action" in
  setup) steps="uv tool install --force \"omnigent[databricks] @ git+https://github.com/omnigent-ai/omnigent.git@$commit\"
\$omni --version
\$omni login $url/omnigent
\$omni host --background --no-open --non-interactive
\$omni host status" ;;
  status) steps='$omni --version; $omni host status' ;;
  stop) steps='$omni host stop' ;;
  remove) steps='[ -x "$omni" ] && $omni host stop || true; rm -rf $HOME/.omnigent-main; echo removed ~/.omnigent-main' ;;
  *) echo "unknown action: $action" >&2; exit 2 ;;
esac

# The CLI quotes each argument for ssh, so the script travels as one argument to bash -lc.
exec databricks sandbox ssh "$sandbox" -p "$profile" -- bash -lc "set -eu
$env
$steps"
