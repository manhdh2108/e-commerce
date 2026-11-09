-- Kiểm thử measure (PLAN 4.8.7) — QUY TẮC trên kho: công thức từng dòng, giá vốn đúng phiên bản, bridge,
-- tính liên tục tồn kho, semi-additive và non-additive. Các cột "vi phạm" kỳ vọng = 0.

\echo == 1. Fact_Order_Item: số dòng VI PHẠM công thức (kỳ vọng 0)
SELECT count(*) AS dong,
       count(*) FILTER (WHERE gross_amount <> quantity * unit_price) AS gross,
       count(*) FILTER (WHERE list_amount <> quantity * list_price) AS list_amount,
       count(*) FILTER (WHERE list_discount_amount <> list_amount - gross_amount) AS list_disc,
       count(*) FILTER (WHERE net_revenue <> gross_amount - discount_amount) AS net,
       count(*) FILTER (WHERE commission_amount <> round(net_revenue * commission_rate, 2)) AS commission,
       count(*) FILTER (WHERE seller_net_amount <> net_revenue - commission_amount) AS seller_net,
       count(*) FILTER (WHERE gross_margin_est <> net_revenue - cost_amount_est) AS margin,
       count(*) FILTER (WHERE discount_amount < 0 OR discount_amount > gross_amount) AS disc_range,
       count(*) FILTER (WHERE commission_amount > net_revenue OR commission_rate NOT BETWEEN 0 AND 1) AS comm_range,
       count(*) FILTER (WHERE cost_amount_est IS NULL) AS cost_null
FROM dw.fact_order_item;
\echo -- thông tin: dòng có giá niêm yết < giá bán (DQ-11 WARN), dòng lãi gộp ước tính âm
SELECT count(*) FILTER (WHERE list_price < unit_price) AS list_lt_unit, count(*) FILTER (WHERE gross_margin_est < 0) AS margin_am
FROM dw.fact_order_item;

\echo == 2. cost_amount_est = quantity × unit_cost_est của ĐÚNG phiên bản sản phẩm tại ngày hoàn tất (kỳ vọng 0)
SELECT count(*) AS mismatch FROM dw.fact_order_item f JOIN dw.dim_product p USING (product_key)
WHERE f.cost_amount_est <> f.quantity * p.unit_cost_est
   OR to_date(f.date_key::text, 'YYYYMMDD') < p.valid_from OR to_date(f.date_key::text, 'YYYYMMDD') >= p.valid_to;
\echo == 3. unit_cost_est = round_1000(giá × cost_ratio nhóm danh mục) (PLAN 4.5) (kỳ vọng 0)
SELECT count(*) AS mismatch FROM dw.dim_product p
JOIN stg.product s ON s.batch_id = (SELECT max(batch_id) FROM audit.batch_log WHERE status = 'SUCCESS') AND s.product_id = p.product_id
WHERE p.is_current AND p.product_key > 0 AND p.unit_cost_est <> round(s.list_price * s.cost_ratio / 1000) * 1000;

\echo == 4. Bridge: Σ phân bổ = Σ discount dòng có voucher; dòng không voucher không có giảm giá; Σ weight = 1
SELECT (SELECT sum(f.discount_amount * b.weighting_factor) FROM dw.fact_order_item f
        JOIN dw.bridge_promotion_group b USING (promotion_group_key)) AS phan_bo,
       (SELECT sum(discount_amount) FROM dw.fact_order_item WHERE promotion_group_key > 0) AS discount_dong_co_voucher,
       (SELECT sum(discount_amount) FROM dw.fact_order_item WHERE promotion_group_key = -1) AS discount_dong_khong_voucher,
       (SELECT count(*) FROM (SELECT 1 FROM dw.bridge_promotion_group GROUP BY promotion_group_key
                              HAVING abs(sum(weighting_factor) - 1) > 0.000001) x) AS nhom_sai_weight;

\echo == 5. Fact_Inventory_Snapshot: công thức (kỳ vọng 0)
SELECT count(*) AS dong,
       count(*) FILTER (WHERE quantity_available <> quantity_on_hand - quantity_reserved) AS available,
       count(*) FILTER (WHERE stockout_flag <> (quantity_available = 0)::int) AS stockout,
       count(*) FILTER (WHERE qty_sold < 0 OR qty_imported < 0 OR qty_returned < 0) AS dong_chay_am
FROM dw.fact_inventory_snapshot;
SELECT count(*) AS inventory_value_mismatch FROM dw.fact_inventory_snapshot f JOIN dw.dim_product p USING (product_key)
WHERE f.inventory_value_est <> f.quantity_on_hand * p.unit_cost_est;
\echo -- tính liên tục: tồn(d) = tồn(d-1) + nhập − bán + trả + điều chỉnh (kỳ vọng broken = 0)
SELECT count(*) AS checked,
       count(*) FILTER (WHERE c.quantity_on_hand <> p.quantity_on_hand + c.qty_imported - c.qty_sold + c.qty_returned + c.qty_adjusted) AS broken
FROM dw.fact_inventory_snapshot c
JOIN dw.fact_inventory_snapshot p ON p.product_key = c.product_key AND p.warehouse_key = c.warehouse_key
 AND to_date(p.date_key::text, 'YYYYMMDD') = to_date(c.date_key::text, 'YYYYMMDD') - 1;

\echo == 6. Semi-additive: tồn cuối kỳ = ngày cuối kỳ, KHÁC SUM qua ngày
SELECT (SELECT sum(quantity_on_hand) FROM dw.fact_inventory_snapshot
        WHERE date_key = (SELECT max(date_key) FROM dw.fact_inventory_snapshot)) AS ton_cuoi_ky_dung,
       (SELECT sum(quantity_on_hand) FROM dw.fact_inventory_snapshot) AS sum_qua_ngay_sai;

\echo == 7. Non-additive: tính lại từ tử/mẫu ở cấp ngày = tính trực tiếp từ atomic; trung bình của tỷ lệ là SAI
WITH d AS (SELECT date_key, sum(net_revenue) AS net, count(DISTINCT order_id) AS n FROM dw.fact_order_item GROUP BY 1)
SELECT round((SELECT sum(net) / sum(n) FROM d), 2) AS aov_tu_tong_ngay,
       round((SELECT sum(net_revenue) / count(DISTINCT order_id) FROM dw.fact_order_item), 2) AS aov_atomic,
       round((SELECT avg(net / n) FROM d), 2) AS aov_tb_cac_ngay_sai,
       round((SELECT sum(commission_amount) / sum(net_revenue) FROM dw.fact_order_item), 6) AS hoa_hong_hieu_dung,
       round((SELECT avg(commission_rate) FROM dw.fact_order_item), 6) AS avg_rate_sai;

\echo == 8. Fact_Ad_Spend: ràng buộc và KPI
SELECT count(*) FILTER (WHERE impressions < clicks) AS imp_lt_clicks, count(*) FILTER (WHERE active_days > 31) AS days_bad,
       round(sum(clicks)::numeric / sum(impressions), 6) AS ctr, round(sum(cost_amount) / sum(clicks), 2) AS cpc,
       round(sum(cost_amount) / sum(impressions) * 1000, 2) AS cpm
FROM dw.fact_ad_spend;

\echo == 9. Hai mốc thời gian bán hàng (kỳ vọng KHÁC nhau, PLAN 4.8.3): xuất kho theo ngày vs số món hoàn tất
SELECT (SELECT sum(qty_sold) FROM dw.fact_inventory_snapshot) AS xuat_kho_sale,
       (SELECT sum(quantity) FROM dw.fact_order_item) AS so_mon_hoan_tat;
