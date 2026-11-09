-- TAB: [P1c] Tu_Dien   (Milestone 3.3: từ điển dữ liệu / metadata)
-- Kỳ vọng: câu đầu ra 200 cột; câu sau là mô tả, nguồn, quy tắc và tính cộng của các cột tiền trong fact bán hàng.

SELECT count(*) AS so_cot_co_mo_ta FROM audit.data_dictionary;

SELECT column_name, data_type, description, additivity
FROM audit.data_dictionary
WHERE table_name = 'fact_order_item' AND column_name IN ('quantity', 'discount_amount', 'net_revenue', 'commission_amount')
ORDER BY ordinal_position;
