-- UC functions the store-ops agent calls as tools, plus the risk view they read.
USE CATALOG {{catalog}};
USE IDENTIFIER({{schema}});

CREATE OR REPLACE FUNCTION stockout_risk_level(days_of_cover DOUBLE, lead_time_days INT)
RETURNS STRING
COMMENT 'Stock-out risk for a store-SKU: HIGH when cover is shorter than the supplier lead time, MEDIUM within 7 days past it, else LOW.'
RETURN CASE
  WHEN days_of_cover < lead_time_days THEN 'HIGH'
  WHEN days_of_cover < lead_time_days + 7 THEN 'MEDIUM'
  ELSE 'LOW'
END;

CREATE OR REPLACE FUNCTION reorder_qty(
  on_hand INT, on_order INT, avg_daily_units DOUBLE, lead_time_days INT,
  review_days INT, safety_days INT, case_pack INT)
RETURNS INT
COMMENT 'Units to order, rounded up to whole cases, to cover lead time + review period + safety days at the given daily demand.'
RETURN CAST(
  ceil(greatest(0, avg_daily_units * (lead_time_days + review_days + safety_days) - on_hand - on_order) / case_pack)
  * case_pack AS INT);

CREATE OR REPLACE VIEW v_stockout_risk
COMMENT 'One row per store and SKU: 14-day average demand, days of cover, stock-out risk, and the draft reorder (7-day review, 3 safety days).'
AS SELECT
  i.store_id, s.store_name, s.region, s.store_format,
  i.sku_id, p.product_name, p.category, p.is_promo,
  p.supplier_id, sp.supplier_name, p.lead_time_days, p.case_pack, p.unit_cost,
  i.on_hand, i.on_order,
  round(d.avg_daily_units_14d, 2) AS avg_daily_units_14d,
  round((i.on_hand + i.on_order) / d.avg_daily_units_14d, 1) AS days_of_cover,
  -- Risk uses the same rounded cover the view shows, so a recomputed what-if matches it.
  stockout_risk_level(round((i.on_hand + i.on_order) / d.avg_daily_units_14d, 1), p.lead_time_days) AS risk_level,
  reorder_qty(i.on_hand, i.on_order, d.avg_daily_units_14d, p.lead_time_days, 7, 3, p.case_pack) AS reorder_units,
  round(reorder_qty(i.on_hand, i.on_order, d.avg_daily_units_14d, p.lead_time_days, 7, 3, p.case_pack) * p.unit_cost, 2) AS est_order_cost
FROM inventory_snapshot i
JOIN stores s ON s.store_id = i.store_id
JOIN products p ON p.sku_id = i.sku_id
JOIN suppliers sp ON sp.supplier_id = p.supplier_id
JOIN (
  SELECT sd.store_id, sd.sku_id, greatest(avg(sd.units_sold), 0.1) AS avg_daily_units_14d
  FROM sales_daily sd
  CROSS JOIN demo_config cfg
  WHERE sd.sale_date > date_sub(cfg.as_of_date, 14)
  GROUP BY sd.store_id, sd.sku_id
) d ON d.store_id = i.store_id AND d.sku_id = i.sku_id;

-- Row limit uses ROW_NUMBER + WHERE: LIMIT and QUALIFY can't take a function parameter.
CREATE OR REPLACE FUNCTION stores_at_risk(p_region STRING, p_category STRING, p_max_rows INT)
RETURNS TABLE (
  store_id STRING, store_name STRING, region STRING,
  high_risk_skus BIGINT, medium_risk_skus BIGINT, draft_order_cost DOUBLE, worst_sku STRING)
COMMENT 'Stores ranked by HIGH-risk SKU count. Pass NULL for p_region or p_category to include all; p_max_rows caps the rows.'
RETURN SELECT store_id, store_name, region, high_risk_skus, medium_risk_skus, draft_order_cost, worst_sku
FROM (
  SELECT *, ROW_NUMBER() OVER (ORDER BY high_risk_skus DESC, draft_order_cost DESC, store_id) AS rank_in_list
  FROM (
    SELECT
      v.store_id, v.store_name, v.region,
      count_if(v.risk_level = 'HIGH') AS high_risk_skus,
      count_if(v.risk_level = 'MEDIUM') AS medium_risk_skus,
      round(sum(CASE WHEN v.risk_level IN ('HIGH', 'MEDIUM') THEN v.est_order_cost ELSE 0 END), 2) AS draft_order_cost,
      min_by(v.sku_id, v.days_of_cover / v.lead_time_days) AS worst_sku
    FROM v_stockout_risk v
    WHERE (stores_at_risk.p_region IS NULL OR v.region = stores_at_risk.p_region)
      AND (stores_at_risk.p_category IS NULL OR v.category = stores_at_risk.p_category)
    GROUP BY v.store_id, v.store_name, v.region
  ) per_store
) ranked
WHERE rank_in_list <= stores_at_risk.p_max_rows;

CREATE OR REPLACE FUNCTION replenishment_plan(p_store_id STRING)
RETURNS TABLE (
  sku_id STRING, product_name STRING, category STRING, supplier_name STRING, risk_level STRING,
  on_hand INT, on_order INT, avg_daily_units_14d DOUBLE, days_of_cover DOUBLE, lead_time_days INT,
  case_pack INT, reorder_units INT, est_order_cost DOUBLE, needs_escalation BOOLEAN)
COMMENT 'Draft replenishment order for one store: HIGH and MEDIUM SKUs with a reorder, HIGH first. needs_escalation is true when lead time > 7 days or the line costs over 5000.'
RETURN SELECT
  v.sku_id, v.product_name, v.category, v.supplier_name, v.risk_level,
  v.on_hand, v.on_order, v.avg_daily_units_14d, v.days_of_cover, v.lead_time_days,
  v.case_pack, v.reorder_units, v.est_order_cost,
  v.lead_time_days > 7 OR v.est_order_cost > 5000 AS needs_escalation
FROM v_stockout_risk v
WHERE v.store_id = replenishment_plan.p_store_id
  AND v.risk_level IN ('HIGH', 'MEDIUM')
  AND v.reorder_units > 0
ORDER BY CASE v.risk_level WHEN 'HIGH' THEN 0 ELSE 1 END, v.days_of_cover / v.lead_time_days;
