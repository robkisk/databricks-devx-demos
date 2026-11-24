#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.3.0", "databricks-sdk==0.170.0"]
# ///
"""List the tools each of the agent's MCP endpoints offers you (read-only: initialize, then tools/list).

usage: scripts/mcp_tools.py -p <profile> --catalog <catalog> [--skills-schema agent_skills]

Run it before you trust the allowlists in the agent's config.yaml. Docs and workspaces can disagree:
the Databricks SQL MCP page lists execute_sql_read_only, and the workspace this was verified on didn't
offer it.
"""
import argparse
import asyncio

from databricks.sdk import WorkspaceClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-p", "--profile", required=True)
parser.add_argument("--catalog", required=True)
parser.add_argument("--skills-schema", default="agent_skills")
args = parser.parse_args()

w = WorkspaceClient(profile=args.profile)
endpoints = {
    "uc-skills": f"/ai-gateway/skills/?schema={args.catalog}.{args.skills_schema}",
    "genie": f"/ai-gateway/mcp-services/system.ai.genie_one_mcp?o={w.get_workspace_id()}",
    "dbsql": "/ai-gateway/mcp-services/system.ai.dbsql",
}


async def tool_names(url: str) -> list[str]:
    async with create_mcp_http_client(headers=w.config.authenticate()) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                return sorted(tool.name for tool in (await session.list_tools()).tools)


for name, path in endpoints.items():
    try:
        print(f"{name:10}", ", ".join(asyncio.run(tool_names(w.config.host.rstrip("/") + path))))
    except Exception as exc:  # report and carry on with the next endpoint
        print(f"{name:10} ERROR {type(exc).__name__}: {str(exc)[:300]}")
