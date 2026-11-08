-- PLAN 5.1 — Trạng thái batch theo giai đoạn: RUNNING → EXTRACTED → TRANSFORMED → SUCCESS (hoặc FAILED).
-- Chỉ batch SUCCESS mới được dùng làm mốc watermark cho batch kế tiếp.
ALTER TABLE audit.batch_log DROP CONSTRAINT IF EXISTS batch_log_status_check;
ALTER TABLE audit.batch_log ADD CONSTRAINT batch_log_status_check
  CHECK (status IN ('RUNNING','EXTRACTED','TRANSFORMED','SUCCESS','FAILED'));
ALTER TABLE audit.batch_log ADD COLUMN IF NOT EXISTS source_snapshot text;  -- last_day của mock + thời điểm đọc
COMMENT ON TABLE audit.batch_log IS 'Mỗi lần chạy ETL = 1 batch. watermark_from (không gồm) .. watermark_to (gồm) là ngày mô phỏng đã hoàn tất.';
