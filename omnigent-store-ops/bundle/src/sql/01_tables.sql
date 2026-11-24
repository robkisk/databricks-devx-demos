-- Store stock-out demo data: deterministic, generated in SQL (xxhash64 noise), no external files.
-- Parameters {{catalog}}, {{schema}}, {{customer_name}}, and {{as_of_date}} come from the job's sql_task.
USE CATALOG {{catalog}};
USE IDENTIFIER({{schema}});

-- as_of_date anchors every date. The bundle pins it (variable as_of_date), so the numbers don't drift.
CREATE OR REPLACE TABLE demo_config
COMMENT 'Demo settings: customer name and the as-of date every other table is anchored to.'
AS SELECT {{customer_name}} AS customer_name, to_date({{as_of_date}}) AS as_of_date;

-- Region names (keep 4 rows; store_count in stores below is spread evenly across them).
CREATE OR REPLACE TABLE dim_region
COMMENT 'Sales regions.'
AS SELECT * FROM VALUES
  (1, 'Pacific'),
  (2, 'Mountain'),
  (3, 'Central'),
  (4, 'Southeast')
AS t(region_id, region_name);

-- Category names only (keep 8 rows). The numbers set each category's velocity, cost, and
-- supplier lead time; long lead times (> 7 days) drive the escalation story.
CREATE OR REPLACE TABLE dim_category
COMMENT 'Product categories with their demand, cost, and supplier lead-time profile.'
AS SELECT * FROM VALUES
  (1, 'Produce',          30.0, 1.6, 2),
  (2, 'Dairy',            22.0, 2.4, 3),
  (3, 'Bakery',           18.0, 2.8, 1),
  (4, 'Meat and Seafood', 12.0, 9.5, 3),
  (5, 'Frozen',            9.0, 4.2, 6),
  (6, 'Pantry',           10.0, 2.9, 8),
  (7, 'Beverages',        16.0, 3.3, 5),
  (8, 'Household',         6.0, 5.8, 10)
AS t(category_id, category_name, base_daily_units, base_unit_cost, base_lead_time_days);

-- Two suppliers per category; the second is 2 days slower.
CREATE OR REPLACE TABLE suppliers
COMMENT 'Suppliers, two per category, with their replenishment lead time in days.'
AS SELECT
  format_string('SUP-%02d', (c.category_id - 1) * 2 + k) AS supplier_id,
  concat(c.category_name, CASE k WHEN 1 THEN ' Direct' ELSE ' Wholesale' END) AS supplier_name,
  c.category_id,
  c.base_lead_time_days + (k - 1) * 2 AS lead_time_days
FROM dim_category c
CROSS JOIN (SELECT explode(array(1, 2)) AS k);

-- Store count (32 by default), spread round-robin across the regions.
CREATE OR REPLACE TABLE stores
COMMENT 'Stores with region, format, and a size factor that scales demand.'
AS SELECT
  format_string('S-%03d', n) AS store_id,
  concat(r.region_name, ' #', lpad(CAST(n AS STRING), 3, '0')) AS store_name,
  r.region_name AS region,
  CASE WHEN size_factor >= 1.25 THEN 'Superstore' ELSE 'Neighborhood' END AS store_format,
  size_factor
FROM (
  SELECT n, round(0.7 + 0.9 * (abs(xxhash64('store', n)) % 10000) / 10000.0, 2) AS size_factor
  FROM (SELECT CAST(id + 1 AS INT) AS n FROM range(32))
) s
CROSS JOIN (SELECT count(*) AS region_count FROM dim_region) rc
JOIN dim_region r ON r.region_id = ((s.n - 1) % rc.region_count) + 1;

-- SKUs per category (15 by default). SKUs 1 and 2 of each category are on promo.
CREATE OR REPLACE TABLE products
COMMENT 'Products (SKUs) with supplier, case pack, unit cost and price, lead time, and promo flag.'
AS SELECT
  format_string('SKU-%d%02d', c.category_id, k) AS sku_id,
  concat(c.category_name, ' item ', lpad(CAST(k AS STRING), 2, '0')) AS product_name,
  c.category_name AS category,
  sp.supplier_id,
  element_at(array(6, 12, 24), CAST(1 + abs(xxhash64('pack', c.category_id, k)) % 3 AS INT)) AS case_pack,
  round(c.base_unit_cost * (0.6 + 0.8 * (abs(xxhash64('cost', c.category_id, k)) % 10000) / 10000.0), 2) AS unit_cost,
  round(c.base_unit_cost * (0.6 + 0.8 * (abs(xxhash64('cost', c.category_id, k)) % 10000) / 10000.0) * 1.35, 2) AS unit_price,
  sp.lead_time_days,
  round(c.base_daily_units * (0.5 + (abs(xxhash64('velocity', c.category_id, k)) % 10000) / 10000.0), 2) AS base_daily_units,
  k <= 2 AS is_promo
FROM dim_category c
CROSS JOIN (SELECT CAST(id + 1 AS INT) AS k FROM range(15)) skus
JOIN suppliers sp
  ON sp.category_id = c.category_id
 AND sp.supplier_id = format_string('SUP-%02d', (c.category_id - 1) * 2 + 1 + (skus.k % 2));

-- 60 days of store x SKU sales. Weekends sell 25% more; promo SKUs sell 1.8x in the last 10 days.
CREATE OR REPLACE TABLE sales_daily
COMMENT 'Daily units sold and revenue per store and SKU for the 60 days up to as_of_date.'
AS SELECT
  sale_date, store_id, sku_id, units_sold, round(units_sold * unit_price, 2) AS revenue
FROM (
  SELECT
    date_add(cfg.as_of_date, d.day_offset) AS sale_date,
    s.store_id,
    p.sku_id,
    p.unit_price,
    CAST(round(
      p.base_daily_units * s.size_factor
      * CASE WHEN dayofweek(date_add(cfg.as_of_date, d.day_offset)) IN (1, 7) THEN 1.25 ELSE 1.0 END
      * (0.75 + 0.5 * (abs(xxhash64('sales', s.store_id, p.sku_id, d.day_offset)) % 10000) / 10000.0)
      * CASE WHEN p.is_promo AND d.day_offset >= -9 THEN 1.8 ELSE 1.0 END
    ) AS INT) AS units_sold
  FROM stores s
  CROSS JOIN products p
  CROSS JOIN (SELECT explode(sequence(-59, 0)) AS day_offset) d
  CROSS JOIN demo_config cfg
);

-- Today's inventory. Stock was planned on baseline demand: about 6% of store-SKUs start under their
-- lead time; promo SKUs were stocked thin, so the promo lift pushes long-lead ones under too.
CREATE OR REPLACE TABLE inventory_snapshot
COMMENT 'Current on-hand and on-order units per store and SKU, as of as_of_date.'
AS SELECT
  cfg.as_of_date AS snapshot_date,
  s.store_id,
  p.sku_id,
  CAST(round(p.base_daily_units * s.size_factor * 1.07 * planned_cover_days) AS INT) AS on_hand,
  CASE WHEN bucket < 0.06 AND u2 < 0.3 THEN p.case_pack ELSE 0 END AS on_order
FROM (
  SELECT
    s.store_id, p.sku_id, bucket, u2,
    CASE
      WHEN bucket < 0.06 THEN p.lead_time_days * (0.2 + 0.6 * u2)
      WHEN p.is_promo THEN p.lead_time_days + 3 + 8 * u2
      ELSE p.lead_time_days + 8 + 14 * u2
    END AS planned_cover_days
  FROM (
    SELECT
      s.store_id, p.sku_id,
      (abs(xxhash64('inv', s.store_id, p.sku_id)) % 10000) / 10000.0 AS bucket,
      (abs(xxhash64('cover', s.store_id, p.sku_id)) % 10000) / 10000.0 AS u2
    FROM stores s CROSS JOIN products p
  ) x
  JOIN stores s ON s.store_id = x.store_id
  JOIN products p ON p.sku_id = x.sku_id
) plan
JOIN stores s ON s.store_id = plan.store_id
JOIN products p ON p.sku_id = plan.sku_id
CROSS JOIN demo_config cfg;
