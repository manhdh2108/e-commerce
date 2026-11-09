-- Tạo các thay đổi SCD trên nguồn DEMO, mô phỏng nghiệp vụ thay đổi trong khoảng 13/01–22/01/2026.
-- Chỉ chạy trên mock_oltp_demo. Đối tượng được chọn theo thứ tự cố định để tái lập được.
-- Không cần thêm đơn hàng: dùng đơn thật đã có, ở cả hai phía của ngày thay đổi.
BEGIN;

DO $guard$ BEGIN
  IF current_database() <> 'mock_oltp_demo' THEN
    RAISE EXCEPTION 'Script này chỉ được chạy trên mock_oltp_demo, đang ở %', current_database();
  END IF;
END $guard$;

DROP SCHEMA IF EXISTS demo CASCADE;
CREATE SCHEMA demo;
CREATE TABLE demo.case_log (
  code text PRIMARY KEY, technique text NOT NULL, entity text NOT NULL, entity_id bigint NOT NULL,
  attr text NOT NULL, old_value text, new_value text, effective_date date NOT NULL, note text
);

CREATE TEMP VIEW done AS
  SELECT o.id AS order_id, o.seller_id, o.customer_id, o.completed_at::date AS d
  FROM orders o WHERE o.order_status = 'Completed' AND o.completed_at::date <= DATE '2026-01-22';

DO $$
DECLARE
  id1 bigint; id2 bigint; id3 bigint; id4 bigint;
  cu1 bigint; cu2 bigint; cu3 bigint; p1 bigint; p2 bigint; sib bigint;
  e date; v text; nv text; sn int; np numeric;
BEGIN
  -- S1: SCD2 + SCD3 — seller Normal → Preferred ngày 16/01
  e := DATE '2026-01-16';
  SELECT d.seller_id INTO id1 FROM done d JOIN sellers s ON s.id = d.seller_id
  WHERE s.tier = 'Normal' AND s.status = 'Active' GROUP BY 1
  HAVING count(*) FILTER (WHERE d.d < e) > 0 AND count(*) FILTER (WHERE d.d >= e) > 0
  ORDER BY least(count(*) FILTER (WHERE d.d < e), count(*) FILTER (WHERE d.d >= e)) DESC, 1 LIMIT 1;
  UPDATE sellers SET tier = 'Preferred', updated_at = e + TIME '10:00' WHERE id = id1;
  INSERT INTO demo.case_log VALUES ('S1', 'SCD2 + SCD3', 'seller', id1, 'tier', 'Normal', 'Preferred', e,
    'Đơn trước 16/01 giữ hạng cũ, từ 16/01 sang hạng mới');

  -- S2: SCD2 — seller đổi tỉnh ngày 17/01
  e := DATE '2026-01-17';
  SELECT d.seller_id INTO id2 FROM done d JOIN sellers s ON s.id = d.seller_id
  WHERE s.status = 'Active' AND d.seller_id <> id1 GROUP BY 1
  HAVING count(*) FILTER (WHERE d.d < e) > 0 AND count(*) FILTER (WHERE d.d >= e) > 0
  ORDER BY least(count(*) FILTER (WHERE d.d < e), count(*) FILTER (WHERE d.d >= e)) DESC, 1 LIMIT 1;
  SELECT province INTO v FROM sellers WHERE id = id2;
  nv := CASE WHEN v = 'Đà Nẵng' THEN 'Hà Nội' ELSE 'Đà Nẵng' END;
  UPDATE sellers SET province = nv, city = nv, updated_at = e + TIME '10:00' WHERE id = id2;
  INSERT INTO demo.case_log VALUES ('S2', 'SCD2', 'seller', id2, 'province', v, nv, e, 'Đơn trước và sau ngày đổi thuộc 2 phiên bản');

  -- S3: SCD1 — seller đổi tên shop ngày 17/01
  SELECT d.seller_id INTO id3 FROM done d JOIN sellers s ON s.id = d.seller_id
  WHERE s.status = 'Active' AND d.seller_id NOT IN (id1, id2) AND d.d > DATE '2026-01-12' GROUP BY 1
  ORDER BY count(*) DESC, 1 LIMIT 1;
  SELECT shop_name INTO v FROM sellers WHERE id = id3;
  UPDATE sellers SET shop_name = v || ' (đổi tên)', updated_at = e + TIME '10:00' WHERE id = id3;
  INSERT INTO demo.case_log VALUES ('S3', 'SCD1', 'seller', id3, 'shop_name', v, v || ' (đổi tên)', e, 'Ghi đè, không thêm phiên bản');

  -- S4: SCD2 — khóa seller ngày 21/01, kéo theo sản phẩm ngừng bán (giống MGR-02).
  -- Chọn seller không có đơn hoàn tất từ 21/01 để không mâu thuẫn nghiệp vụ.
  e := DATE '2026-01-21';
  SELECT d.seller_id INTO id4 FROM done d JOIN sellers s ON s.id = d.seller_id
  WHERE s.status = 'Active' AND d.seller_id NOT IN (id1, id2, id3)
    AND NOT EXISTS (SELECT 1 FROM orders x WHERE x.seller_id = d.seller_id AND x.completed_at::date >= e)
  GROUP BY 1 ORDER BY (SELECT count(*) FROM products p WHERE p.seller_id = d.seller_id), 1 LIMIT 1;
  UPDATE sellers SET status = 'Suspended', updated_at = e + TIME '10:00' WHERE id = id4;
  UPDATE products SET is_active = false, updated_at = e + TIME '10:00' WHERE seller_id = id4 AND is_active;
  GET DIAGNOSTICS sn = ROW_COUNT;
  INSERT INTO demo.case_log VALUES ('S4', 'SCD2', 'seller', id4, 'status', 'Active', 'Suspended', e, sn || ' sản phẩm chuyển is_active = false');

  -- C1: SCD2 — khách đổi tỉnh đúng ngày đơn cuối (có đơn trước và từ ngày đó)
  SELECT d.customer_id, max(d.d) INTO cu1, e FROM done d WHERE d.customer_id IS NOT NULL GROUP BY 1
  HAVING min(d.d) < max(d.d) AND max(d.d) BETWEEN DATE '2026-01-14' AND DATE '2026-01-22'
  ORDER BY count(*) DESC, 1 LIMIT 1;
  SELECT province INTO v FROM customers WHERE id = cu1;
  nv := CASE WHEN v = 'Đà Nẵng' THEN 'Hà Nội' ELSE 'Đà Nẵng' END;
  UPDATE customers SET province = nv, city = nv, updated_at = e + TIME '00:00' WHERE id = cu1;
  INSERT INTO demo.case_log VALUES ('C1', 'SCD2', 'customer', cu1, 'province', v, nv, e, 'Doanh thu theo tỉnh lúc mua khác tỉnh hiện tại');

  -- C2: SCD1 — khách đổi tên
  e := DATE '2026-01-17';
  SELECT d.customer_id INTO cu2 FROM done d WHERE d.customer_id IS NOT NULL AND d.customer_id <> cu1 AND d.d > DATE '2026-01-12'
  GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1;
  SELECT full_name INTO v FROM customers WHERE id = cu2;
  UPDATE customers SET full_name = v || ' (đổi tên)', updated_at = e + TIME '10:00' WHERE id = cu2;
  INSERT INTO demo.case_log VALUES ('C2', 'SCD1', 'customer', cu2, 'full_name', v, v || ' (đổi tên)', e, 'Ghi đè, không thêm phiên bản');

  -- C3: Mini-dimension — khách Silver → Gold, có đơn ở batch cũ và batch mới
  SELECT d.customer_id INTO cu3 FROM done d JOIN customers c ON c.id = d.customer_id
  WHERE c.membership_tier = 'Silver' AND d.customer_id NOT IN (cu1, cu2) GROUP BY 1
  HAVING count(*) FILTER (WHERE d.d <= DATE '2026-01-12') > 0 AND count(*) FILTER (WHERE d.d > DATE '2026-01-12') > 0
  ORDER BY count(*) DESC, 1 LIMIT 1;
  UPDATE customers SET membership_tier = 'Gold', updated_at = e + TIME '10:00' WHERE id = cu3;
  INSERT INTO demo.case_log VALUES ('C3', 'Mini-dimension', 'customer', cu3, 'membership_tier', 'Silver', 'Gold', e,
    'dim_customer không thêm dòng; đơn ở batch mới mang hồ sơ hạng Gold');

  -- P1: SCD2 — sản phẩm giảm giá niêm yết 10% ngày 16/01
  e := DATE '2026-01-16';
  SELECT i.product_id INTO p1 FROM order_items i JOIN done d ON d.order_id = i.order_id
  JOIN products p ON p.id = i.product_id WHERE p.seller_id NOT IN (id1, id2, id3, id4) GROUP BY 1
  HAVING count(*) FILTER (WHERE d.d < e) > 0 AND count(*) FILTER (WHERE d.d >= e) > 0
  ORDER BY least(count(*) FILTER (WHERE d.d < e), count(*) FILTER (WHERE d.d >= e)) DESC, 1 LIMIT 1;
  SELECT price INTO np FROM products WHERE id = p1;
  UPDATE products SET price = round(np * 0.9 / 1000) * 1000, updated_at = e + TIME '10:00' WHERE id = p1;
  INSERT INTO demo.case_log VALUES ('P1', 'SCD2', 'product', p1, 'list_price', np::numeric(18,2)::text,
    (round(np * 0.9 / 1000) * 1000)::numeric(18,2)::text, e, 'Giá vốn ước tính của phiên bản mới cũng đổi');

  -- P2: SCD2 — sản phẩm chuyển sang danh mục lá khác cùng danh mục cha, ngày 18/01
  e := DATE '2026-01-18';
  SELECT i.product_id, min(s.id) INTO p2, sib FROM order_items i JOIN done d ON d.order_id = i.order_id
  JOIN products p ON p.id = i.product_id JOIN categories c ON c.id = p.category_id
  JOIN categories s ON s.parent_id = c.parent_id AND s.id <> c.id
  WHERE i.product_id <> p1 AND p.seller_id NOT IN (id1, id2, id3, id4) GROUP BY 1
  HAVING count(*) FILTER (WHERE d.d < e) > 0 AND count(*) FILTER (WHERE d.d >= e) > 0
  ORDER BY least(count(*) FILTER (WHERE d.d < e), count(*) FILTER (WHERE d.d >= e)) DESC, 1 LIMIT 1;
  SELECT category_id::text INTO v FROM products WHERE id = p2;
  UPDATE products p SET category_id = sib, category_name = c.category_name, updated_at = e + TIME '10:00'
  FROM categories c WHERE p.id = p2 AND c.id = sib;
  INSERT INTO demo.case_log VALUES ('P2', 'SCD2', 'product', p2, 'category_id', v, sib::text, e, 'Doanh thu danh mục tách theo ngày chuyển');

  IF EXISTS (SELECT 1 FROM demo.case_log WHERE entity_id IS NULL) THEN RAISE EXCEPTION 'Thiếu đối tượng demo'; END IF;
END $$;

DROP VIEW done;
COMMIT;

\pset pager off
SELECT code, technique, entity, entity_id, attr, old_value, new_value, effective_date, note FROM demo.case_log ORDER BY code;
