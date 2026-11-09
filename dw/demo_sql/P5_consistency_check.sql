-- TAB: [P5] Consistency_Check   (màn hình tổng duyệt — MỘT câu duy nhất, ~1,3 giây)
-- 21 kiểm tra, mỗi dòng PASS khi gia_tri = ky_vong. Định nghĩa: dw/sql/40_mart/402_consistency.sql
-- (view tạo bằng: bash dw/sql/run_ddl.sh — idempotent).

SELECT nhom, kiem_tra, gia_tri, ky_vong, ket_qua FROM mart.v_consistency_check;

-- Tóm tắt: kỳ vọng 21 PASS
SELECT ket_qua, count(*) FROM mart.v_consistency_check GROUP BY 1;

-- Ca cụ thể: fact trước/sau ngày seller đổi hạng gắn đúng phiên bản
-- Kỳ vọng: 9455 có 13 dòng (3.108.000 đ) Normal và 3 dòng (511.000 đ) Mall; 332670 có 33 dòng (20.425.209 đ) Normal và 2 dòng (1.224.000 đ) Mall
SELECT s.seller_id, s.tier, s.valid_from, s.valid_to, s.is_current, count(f.*) AS dong_ban, sum(f.net_revenue) AS doanh_thu
FROM dw.dim_seller s LEFT JOIN dw.fact_order_item f USING (seller_key)
WHERE s.seller_id IN (332670, 9455) GROUP BY 1,2,3,4,5 ORDER BY 1,3;
