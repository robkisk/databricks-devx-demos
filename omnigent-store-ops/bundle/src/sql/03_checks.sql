-- Build checks: the job fails here if the data no longer tells the stock-out story.
USE CATALOG {{catalog}};
USE IDENTIFIER({{schema}});

SELECT assert_true(
  (SELECT count(*) FROM inventory_snapshot) = (SELECT count(*) FROM stores) * (SELECT count(*) FROM products),
  'inventory_snapshot must hold one row per store and SKU');

SELECT assert_true(high_share BETWEEN 0.02 AND 0.15,
  concat('HIGH-risk share ', CAST(round(high_share, 4) AS STRING), ' is outside 2-15%'))
FROM (SELECT avg(CASE WHEN risk_level = 'HIGH' THEN 1.0 ELSE 0.0 END) AS high_share FROM v_stockout_risk);

SELECT assert_true((SELECT count(*) FROM stores_at_risk(NULL, NULL, 5)) = 5,
  'stores_at_risk(NULL, NULL, 5) must return 5 rows');

SELECT assert_true(
  (SELECT count(*) FROM v_stockout_risk WHERE risk_level = 'HIGH' AND (lead_time_days > 7 OR est_order_cost > 5000)) > 0,
  'at least one HIGH-risk line must need escalation');
