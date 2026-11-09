-- TAB: [P1a] Batch_Log   (kết nối dwh, user dw_analyst)
-- Chạy từng câu: đặt con trỏ vào câu, nhấn Ctrl+Enter. Kỳ vọng: batch 4–7 SUCCESS, mốc dữ liệu nối tiếp.

SELECT batch_id, batch_type, status, watermark_from, watermark_to,
       to_char(finished_at,'DD/MM HH24:MI') AS xong_luc
FROM audit.batch_log ORDER BY batch_id;

-- Đối soát của batch mới nhất: 15 dòng, cột passed đều true
SELECT check_code, description, source_value, target_value, passed
FROM audit.reconciliation WHERE batch_id = (SELECT max(batch_id) FROM audit.batch_log WHERE status = 'SUCCESS')
ORDER BY check_code;
