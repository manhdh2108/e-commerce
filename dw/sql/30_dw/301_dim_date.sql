-- PLAN 4.2 — Dim_Date, Dim_Month (tĩnh, sinh 2025-01-01 .. 2027-12-31). Chạy bằng dw_etl trên dwh.
-- Idempotent: tạo nếu chưa có, nạp bằng ON CONFLICT DO NOTHING.

CREATE TABLE IF NOT EXISTS dw.dim_month (
  month_key      int PRIMARY KEY,                 -- yyyymm
  year           smallint NOT NULL,
  quarter        smallint NOT NULL CHECK (quarter BETWEEN 1 AND 4),
  month          smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
  month_label    text NOT NULL,                   -- 'T01/2026'
  quarter_label  text NOT NULL,                   -- 'Q1/2026'
  first_date     date NOT NULL,
  last_date      date NOT NULL,
  days_in_month  smallint NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_date (
  date_key       int PRIMARY KEY,                 -- yyyymmdd; -1/0 không dùng cho ngày
  full_date      date NOT NULL UNIQUE,
  day_of_month   smallint NOT NULL,
  day_of_week    smallint NOT NULL,               -- ISO: 1 = Thứ Hai .. 7 = Chủ Nhật
  day_name       text NOT NULL,
  iso_week       smallint NOT NULL,
  iso_year       smallint NOT NULL,
  month_key      int NOT NULL REFERENCES dw.dim_month (month_key),
  month          smallint NOT NULL,
  month_name     text NOT NULL,
  quarter        smallint NOT NULL,
  year           smallint NOT NULL,
  is_weekend     boolean NOT NULL,
  is_holiday     boolean NOT NULL,
  holiday_name   text,
  is_double_day  boolean NOT NULL,                -- 1/1, 2/2, …, 12/12 (ngày đôi mua sắm)
  is_month_end   boolean NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_dim_date_month ON dw.dim_date (month_key);

INSERT INTO dw.dim_month
SELECT to_char(m, 'YYYYMM')::int, extract(year FROM m), extract(quarter FROM m), extract(month FROM m),
       'T' || to_char(m, 'MM/YYYY'), 'Q' || extract(quarter FROM m) || '/' || extract(year FROM m),
       m::date, (m + interval '1 month - 1 day')::date,
       extract(day FROM (m + interval '1 month - 1 day'))
FROM generate_series('2025-01-01'::date, '2027-12-01'::date, interval '1 month') AS m
ON CONFLICT (month_key) DO NOTHING;

-- Ngày lễ VN (năm 2026 có ngày âm lịch đã quy đổi; năm khác chỉ các ngày dương lịch cố định).
WITH holidays(hd, name) AS (VALUES
  ('2025-01-01'::date,'Tết Dương lịch'),('2026-01-01','Tết Dương lịch'),('2027-01-01','Tết Dương lịch'),
  ('2026-02-16','Tết Nguyên đán (30 Tết)'),('2026-02-17','Tết Nguyên đán (mùng 1)'),
  ('2026-02-18','Tết Nguyên đán (mùng 2)'),('2026-02-19','Tết Nguyên đán (mùng 3)'),
  ('2026-04-26','Giỗ Tổ Hùng Vương (10/3 âm lịch)'),
  ('2025-04-30','Giải phóng miền Nam'),('2026-04-30','Giải phóng miền Nam'),('2027-04-30','Giải phóng miền Nam'),
  ('2025-05-01','Quốc tế Lao động'),('2026-05-01','Quốc tế Lao động'),('2027-05-01','Quốc tế Lao động'),
  ('2025-09-02','Quốc khánh'),('2026-09-02','Quốc khánh'),('2027-09-02','Quốc khánh'))
INSERT INTO dw.dim_date
SELECT to_char(d, 'YYYYMMDD')::int, d, extract(day FROM d), extract(isodow FROM d),
       (ARRAY['Thứ Hai','Thứ Ba','Thứ Tư','Thứ Năm','Thứ Sáu','Thứ Bảy','Chủ Nhật'])[extract(isodow FROM d)],
       extract(week FROM d), extract(isoyear FROM d), to_char(d, 'YYYYMM')::int, extract(month FROM d),
       'Tháng ' || extract(month FROM d), extract(quarter FROM d), extract(year FROM d),
       extract(isodow FROM d) IN (6, 7), h.name IS NOT NULL, h.name,
       extract(day FROM d) = extract(month FROM d),
       d = (date_trunc('month', d) + interval '1 month - 1 day')::date
FROM generate_series('2025-01-01'::date, '2027-12-31'::date, interval '1 day') AS g(ts)
CROSS JOIN LATERAL (SELECT g.ts::date AS d) x
LEFT JOIN holidays h ON h.hd = x.d
ON CONFLICT (date_key) DO NOTHING;

COMMENT ON TABLE dw.dim_date IS 'Chiều thời gian mức ngày (tĩnh). Grain: 1 ngày. Role-playing: ngày hoàn tất (date_key) và ngày đặt (order_date_key) của Fact_Order_Item; ngày snapshot của Fact_Inventory_Snapshot.';
COMMENT ON COLUMN dw.dim_date.date_key IS 'Khóa ngày dạng yyyymmdd (smart key, dễ partition theo khoảng).';
COMMENT ON COLUMN dw.dim_date.is_double_day IS 'Ngày đôi (ngày = tháng): mùa mua sắm 1/1..12/12.';
COMMENT ON COLUMN dw.dim_date.is_holiday IS 'Ngày lễ VN; 2026 gồm Tết Nguyên đán 16–19/02 và Giỗ Tổ 26/04 (âm lịch quy đổi).';
COMMENT ON TABLE dw.dim_month IS 'Chiều tháng (conformed với dim_date qua month_key). Grain của Fact_Ad_Spend.';
