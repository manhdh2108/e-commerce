-- TAB: [P4] Cach_Ly   (batch 3 = batch có chèn lỗi giả lập; không chèn lại lúc demo)
-- Kỳ vọng: DQ-02 (5), DQ-03 (8), DQ-04 (7), DQ-05 (2), DQ-07 (5), DQ-08 (3), DQ-12 (28), DQ-15 (9), tổng 67.

SELECT rule_code, severity, count(*) AS so_dong
FROM audit.quarantine WHERE batch_id = 3 GROUP BY 1,2 ORDER BY 1;

SELECT source_table, source_pk, rule_code, reason
FROM audit.quarantine WHERE batch_id = 3 AND rule_code IN ('DQ-02','DQ-03') ORDER BY rule_code, source_pk LIMIT 4;
