-- dim:trade_gmv
-- Clean paid orders into dws.trade_gmv
INSERT INTO dws.trade_gmv
SELECT
    o.order_id,
    o.user_id,
    o.pay_amount AS gmv,
    o.pay_time
FROM ods.orders o
WHERE o.status = 'paid'
  AND o.is_deleted = 0;
