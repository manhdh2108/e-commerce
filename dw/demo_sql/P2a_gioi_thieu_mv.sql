-- TAB: [P2a] MV_Gioi_Thieu   (tầng Summary = 8 materialized view của schema mart)
-- Kỳ vọng: 8 MV; cả 8 refresh ở batch SUCCESS mới nhất; mv_inventory_month_product lớn nhất (~18 nghìn dòng).

SELECT schemaname, matviewname, pg_size_pretty(pg_total_relation_size((schemaname||'.'||matviewname)::regclass)) AS dung_luong
FROM pg_matviews WHERE schemaname = 'mart' ORDER BY 2;

SELECT mv_name, batch_id, to_char(refreshed_at,'DD/MM HH24:MI') AS refreshed_at, row_count, seconds
FROM mart.refresh_status ORDER BY seconds DESC;

-- MV bản chất là một câu GROUP BY được lưu sẵn kết quả
SELECT pg_get_viewdef('mart.mv_sales_month_category'::regclass, true);
