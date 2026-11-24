#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["databricks-sdk==0.170.0"]
# ///
"""Print the answers the agent should give, straight from the deployed data.

usage: scripts/expected.py -p <profile> --catalog <catalog> [--schema retail_stockout] [--warehouse-id <id>]

Without --warehouse-id it uses the warehouse named "Serverless Starter Warehouse", as the bundle does.
"""
import argparse
import sys
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-p", "--profile", required=True)
parser.add_argument("--catalog", required=True)
parser.add_argument("--schema", default="retail_stockout")
parser.add_argument("--warehouse-id")
args = parser.parse_args()

w = WorkspaceClient(profile=args.profile)
warehouse_id = args.warehouse_id or next(
    (wh.id for wh in w.warehouses.list() if wh.name == "Serverless Starter Warehouse"), None)
if not warehouse_id:
    sys.exit("no warehouse named 'Serverless Starter Warehouse'; pass --warehouse-id")
s = f"{args.catalog}.{args.schema}"


def rows(sql: str) -> list[list[str]]:
    resp = w.statement_execution.execute_statement(statement=sql, warehouse_id=warehouse_id, wait_timeout="50s")
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        sys.exit(f"query failed: {resp.status.error.message if resp.status.error else resp.status.state}\n{sql}")
    return resp.result.data_array or []


print("as of:", rows(f"SELECT as_of_date FROM {s}.demo_config")[0][0])

print("\nQ1. Pacific top 3 (stores_at_risk, then replenishment_plan per store)")
print(f"  {'store':6} {'HIGH':>4} {'MED':>4} {'lines':>5} {'long-lead':>9} {'draft cost':>11}")
for store, high, med, cost in rows(
        f"SELECT store_id, high_risk_skus, medium_risk_skus, draft_order_cost "
        f"FROM {s}.stores_at_risk('Pacific', NULL, 3)"):
    lines, long_lead = rows(
        f"SELECT count(*), count_if(lead_time_days > 7) FROM {s}.replenishment_plan('{store}')")[0]
    print(f"  {store:6} {high:>4} {med:>4} {lines:>5} {long_lead:>9} {float(cost):>11,.2f}")

lines, high, med, units, cost = rows(
    f"SELECT count(*), count_if(risk_level = 'HIGH'), count_if(risk_level = 'MEDIUM'), sum(reorder_units), "
    f"round(sum(est_order_cost), 2) FROM {s}.replenishment_plan('S-007')")[0]
print(f"\nQ2. S-007 draft order: {lines} lines ({high} HIGH, {med} MEDIUM), {int(units):,} units, ${float(cost):,.2f}")

# Last 30 days of Produce units, split into two 15-day halves, plus the step when the promo starts.
daily = rows(
    f"SELECT sd.sale_date, sum(sd.units_sold) FROM {s}.sales_daily sd JOIN {s}.products p ON p.sku_id = sd.sku_id "
    f"WHERE p.category = 'Produce' AND sd.sale_date > date_sub((SELECT as_of_date FROM {s}.demo_config), 30) "
    f"GROUP BY sd.sale_date ORDER BY sd.sale_date")
units = [int(u) for _, u in daily]
first, second = sum(units[:15]), sum(units[15:])
# The promo lift starts 9 days before as_of_date (the last 10 days); weekends add noise day to day.
before, after = units[:-10], units[-10:]
step = 100 * ((sum(after) / len(after)) / (sum(before) / len(before)) - 1)
print(f"\nQ3. Produce, last 30 days: second half {100 * (second / first - 1):+.1f}% vs first half; "
      f"average daily units step up {step:+.1f}% from {daily[-10][0]}, when the promo starts")

print("\nQ4. A SET statement sent through execute_sql should come back 'Denied by policy: ...' with no statement ID.")
