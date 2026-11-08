-- PLAN 5.1 / 5.3.4 / 5.6 / 4.7 — Bảng audit (lịch sử nạp, cách ly, chất lượng, đối soát) và từ điển dữ liệu.

CREATE TABLE IF NOT EXISTS audit.batch_log (
  batch_id        bigserial PRIMARY KEY,
  batch_type      text        NOT NULL DEFAULT 'INCREMENTAL',  -- INCREMENTAL | RERUN | TEST_ERRORS
  status          text        NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','SUCCESS','FAILED')),
  watermark_from  date,                                         -- ngày mô phỏng (không gồm)
  watermark_to    date,                                         -- ngày mô phỏng (gồm) = last_day
  started_at      timestamp   NOT NULL DEFAULT now(),
  finished_at     timestamp,
  rerun_of        bigint REFERENCES audit.batch_log (batch_id),
  message         text
);

CREATE TABLE IF NOT EXISTS audit.batch_table_log (
  batch_id        bigint NOT NULL REFERENCES audit.batch_log (batch_id),
  stage           text   NOT NULL,           -- EXTRACT | TRANSFORM | LOAD
  table_name      text   NOT NULL,
  rows_read       bigint,
  rows_valid      bigint,
  rows_warn       bigint,
  rows_quarantined bigint,
  rows_deduplicated bigint,
  rows_written    bigint,
  checksum        text,                      -- md5 nội dung (raw) để chứng minh nạp lại cùng dữ liệu
  logged_at       timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (batch_id, stage, table_name)
);

CREATE TABLE IF NOT EXISTS audit.quarantine (
  quarantine_id     bigserial PRIMARY KEY,
  batch_id          bigint NOT NULL REFERENCES audit.batch_log (batch_id),
  source_table      text   NOT NULL,
  source_pk         text   NOT NULL,
  rule_code         text   NOT NULL,         -- DQ-01..DQ-20
  severity          text   NOT NULL CHECK (severity IN ('ERROR','WARN')),
  reason            text   NOT NULL,
  payload           jsonb  NOT NULL,
  quarantined_at    timestamp NOT NULL DEFAULT now(),
  resolved_batch_id bigint REFERENCES audit.batch_log (batch_id)
);
CREATE INDEX IF NOT EXISTS ix_quarantine_batch ON audit.quarantine (batch_id, rule_code);
CREATE INDEX IF NOT EXISTS ix_quarantine_open  ON audit.quarantine (source_table, source_pk) WHERE resolved_batch_id IS NULL;

CREATE TABLE IF NOT EXISTS audit.dq_result (
  batch_id     bigint NOT NULL REFERENCES audit.batch_log (batch_id),
  rule_code    text   NOT NULL,
  table_name   text   NOT NULL,
  severity     text   NOT NULL,
  rows_checked bigint NOT NULL,
  rows_failed  bigint NOT NULL,
  PRIMARY KEY (batch_id, rule_code, table_name)
);

CREATE TABLE IF NOT EXISTS audit.reconciliation (
  batch_id     bigint  NOT NULL REFERENCES audit.batch_log (batch_id),
  check_code   text    NOT NULL,             -- RC-01..RC-07
  description  text    NOT NULL,
  source_value numeric,
  target_value numeric,
  passed       boolean NOT NULL,
  checked_at   timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (batch_id, check_code)
);

-- Thông tin bổ sung cho từ điển (nguồn OLTP, quy tắc, tính cộng, SCD) — điền theo cột
CREATE TABLE IF NOT EXISTS audit.column_lineage (
  schema_name  text NOT NULL,
  table_name   text NOT NULL,
  column_name  text NOT NULL,
  source       text,           -- bảng.cột OLTP / crawler
  rule         text,           -- công thức / quy tắc biến đổi
  additivity   text CHECK (additivity IN ('A','SA','NA','KEY','ATTR','TECH')),
  scd_type     text,           -- '1', '2', '3', 'mini', '-'
  PRIMARY KEY (schema_name, table_name, column_name)
);

-- Từ điển dữ liệu: ghép catalog (kiểu, NULL, mô tả COMMENT) với lineage
CREATE OR REPLACE VIEW audit.data_dictionary AS
SELECT c.table_schema AS schema_name, c.table_name, c.ordinal_position, c.column_name,
       CASE WHEN c.data_type = 'numeric' THEN format('numeric(%s,%s)', c.numeric_precision, c.numeric_scale)
            WHEN c.data_type = 'character' THEN format('char(%s)', c.character_maximum_length)
            ELSE c.data_type END AS data_type,
       c.is_nullable = 'YES' AS nullable,
       col_description(format('%I.%I', c.table_schema, c.table_name)::regclass, c.ordinal_position) AS description,
       l.source, l.rule, l.additivity, l.scd_type,
       obj_description(format('%I.%I', c.table_schema, c.table_name)::regclass, 'pg_class') AS table_description
FROM information_schema.columns c
JOIN pg_class pc ON pc.relname = c.table_name
JOIN pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = c.table_schema
LEFT JOIN audit.column_lineage l ON (l.schema_name, l.table_name, l.column_name) = (c.table_schema, c.table_name, c.column_name)
WHERE c.table_schema = 'dw' AND NOT pc.relispartition;
