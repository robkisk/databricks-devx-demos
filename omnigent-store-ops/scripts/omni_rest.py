#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["databricks-sdk==0.170.0"]
# ///
"""Drive Omnigent on Databricks sessions through its REST API (/api/2.0/omnigent/v1).

usage: scripts/omni_rest.py -p <profile> <command> ...
  hosts                                     your registered hosts: id, name, status
  agents                                    the agents you installed: id, name, version
  session --agent <name> (--host-id <id> | --managed) [--workspace /home/sandbox-agent] [--title ...]
                                            create a session and print its id
  ask <session-id> "<question>" [--timeout 600]
                                            send a message, wait for the turn, print its tool calls and reply
  show <session-id>                         print the whole session: tool calls, replies, status, cost
  sessions [--agent <name>]                 list your sessions
  delete <session-id> [...]                 delete sessions

`omni` has no flag that places a session on a specific remote host, so `session` creates one here.
The server runs several replicas. A request for a session on your own host can come back
`wrong_replica` until it carries X-Databricks-Omnigent-Slice-Key: <host-id>. `databricks api` can't
send custom headers, so this script uses the SDK's api_client.do and retries with that header, taking
the host id from --slice-key or from the session list.
"""
import argparse
import json
import sys
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError

BASE = "/api/2.0/omnigent/v1"
DONE = {"idle", "completed", "failed", "error", "waiting"}

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-p", "--profile", required=True, help="your Databricks CLI profile for the workspace")
parser.add_argument("--slice-key", help="host id to route by when the server answers wrong_replica")
sub = parser.add_subparsers(dest="command", required=True)
sub.add_parser("hosts")
sub.add_parser("agents")
p = sub.add_parser("session")
p.add_argument("--agent", required=True, help="agent name or id")
where = p.add_mutually_exclusive_group(required=True)
where.add_argument("--host-id", help="a host you registered, from `hosts`")
where.add_argument("--managed", action="store_true", help="let the platform start a managed Sandbox host")
p.add_argument("--workspace", default="/home/sandbox-agent", help="working directory on the host")
p.add_argument("--title", default="store-ops-analyst demo")
p = sub.add_parser("ask")
p.add_argument("session_id")
p.add_argument("text")
p.add_argument("--timeout", type=int, default=600)
p = sub.add_parser("show")
p.add_argument("session_id")
p = sub.add_parser("sessions")
p.add_argument("--agent")
p = sub.add_parser("delete")
p.add_argument("session_ids", nargs="+")
args = parser.parse_args()

w = WorkspaceClient(profile=args.profile)
slice_key = args.slice_key


def call(method: str, path: str, body: dict | None = None, session_id: str | None = None) -> dict:
    """One API call. On wrong_replica, retry with the slice key: --slice-key, or the session's host."""
    global slice_key
    headers = {"Content-Type": "application/json"}
    try:
        return w.api_client.do(method, BASE + path, headers=headers, body=body) or {}
    except DatabricksError as exc:
        if "wrong_replica" not in str(exc):
            raise
        if not slice_key and session_id:
            slice_key = next((s.get("host_id") for s in list_sessions() if s["id"] == session_id), None)
        if not slice_key:
            raise SystemExit(f"{exc}\nRetry with --slice-key <host-id> (see `hosts`).") from exc
        headers["X-Databricks-Omnigent-Slice-Key"] = slice_key
        return w.api_client.do(method, BASE + path, headers=headers, body=body) or {}


def list_sessions() -> list[dict]:
    """Every session you own, following the list's has_more / last_id cursor."""
    found, after = [], None
    while True:
        page = w.api_client.do("GET", BASE + "/sessions", query={"limit": 100, **({"after": after} if after else {})}) or {}
        found += page.get("data", [])
        if not page.get("has_more") or not page.get("last_id") or page["last_id"] == after:
            return found
        after = page["last_id"]


def get_session(session_id: str) -> dict:
    global slice_key
    session = call("GET", f"/sessions/{session_id}", session_id=session_id)
    slice_key = slice_key or session.get("host_id")
    return session


def print_items(items: list[dict]) -> None:
    for item in items:
        data = item.get("data") or {}
        if item["type"] == "function_call":
            print(f"  tool: {data.get('name')}  {str(data.get('arguments'))[:160]}")
        elif item["type"] == "message":
            text = "\n".join(c.get("text", "") for c in data.get("content") or [])
            print(f"----- {data.get('role')} -----\n{text}")


def print_status(session: dict) -> None:
    pending = session.get("pending_elicitations") or []
    print(f"----- status={session['status']} pending_approvals={len(pending)} "
          f"cost_usd={session.get('total_cost_usd')} last_error={session.get('last_task_error') or 'none'}")
    if pending:
        print("The agent is waiting for an answer (a pending approval leaves the session at `running`):")
        print(json.dumps(pending, indent=2)[:2000])


if args.command == "hosts":
    for host in call("GET", "/hosts").get("hosts", []):
        print(host["host_id"], host.get("name"), host.get("status"))
elif args.command == "agents":
    for agent in call("GET", "/agents?scope=user&limit=50").get("data", []):
        print(agent["id"], agent["name"], f"v{agent.get('version')}")
elif args.command == "session":
    agents = [a for a in call("GET", "/agents?scope=user&limit=50").get("data", []) if args.agent in (a["id"], a["name"])]
    if not agents:
        sys.exit(f"no agent named {args.agent!r}; install it with `omnigent agent add`")
    body = {"agent_id": agents[0]["id"], "title": args.title}
    if args.managed:
        body["host_type"] = "managed"
    else:
        body |= {"host_type": "external", "host_id": args.host_id, "workspace": args.workspace}
        slice_key = slice_key or args.host_id
    print(call("POST", "/sessions", body)["id"])
elif args.command == "ask":
    before = len(get_session(args.session_id).get("items") or [])
    call("POST", f"/sessions/{args.session_id}/events",
         {"type": "message", "data": {"role": "user", "content": [{"type": "input_text", "text": args.text}]}},
         session_id=args.session_id)
    start = time.monotonic()
    while True:
        time.sleep(5)
        session = get_session(args.session_id)
        waited = time.monotonic() - start
        # Wait for the turn's reply itself, not only the status: the status can read idle before the turn
        # starts, and a finished turn's items can land a poll after the status flips back.
        replied = any(i["type"] == "message" and (i.get("data") or {}).get("role") == "assistant"
                      for i in (session.get("items") or [])[before:])
        status = session["status"]
        if session.get("pending_elicitations") or status in ("failed", "error"):
            break
        if status in DONE and (replied or waited > 120):
            break
        if waited > args.timeout:
            print(f"timed out after {waited:.0f}s with status={status}")
            break
    print_items((session.get("items") or [])[before:])
    print(f"----- turn took {time.monotonic() - start:.0f}s")
    print_status(session)
elif args.command == "show":
    session = get_session(args.session_id)
    print_items(session.get("items") or [])
    print_status(session)
elif args.command == "sessions":
    for s in list_sessions():
        if not args.agent or s.get("agent_name") == args.agent:
            print(s["id"], s.get("agent_name"), s.get("status"), s.get("title"))
elif args.command == "delete":
    for session_id in args.session_ids:
        call("DELETE", f"/sessions/{session_id}", session_id=session_id)
        print("deleted", session_id)
