from .storage import UnitOfWork


class BusinessValidator:
    """Independent arithmetic and stock checks for implemented workflows."""

    def __init__(self, db):
        self.db = db

    def report(self, job=None):
        errors = []
        checks = []
        with self.db.business.connect() as c:
            u = UnitOfWork(self.db, c)
            movements = u.rows("inventory_movements")
            inventory = u.rows("inventory_levels")
            for row in inventory:
                balance = sum(
                    m["quantity_change"]
                    for m in movements
                    if m["sku"] == row["sku"]
                    and m["warehouse_id"] == row["warehouse_id"]
                )
                if (
                    balance != row["quantity_on_hand"]
                    or not 0 <= row["quantity_reserved"] <= row["quantity_on_hand"]
                ):
                    errors.append(
                        {
                            "table": "inventory_levels",
                            "id": row["id"],
                            "reason": "Tồn không khớp sổ nhập/xuất hoặc giữ vượt tồn.",
                        }
                    )
            checks.append("Đối chiếu tồn kho với sổ biến động và lượng giữ")
            items = u.rows("order_items")
            payments = u.rows("payments")
            for o in u.rows("orders"):
                lines = [i for i in items if i["order_id"] == o["id"]]
                net = sum(
                    i["net_amount"] for i in lines if i["item_status"] != "Cancelled"
                )
                expected = net + o["shipping_fee"] - o["shipping_discount_amount"]
                if (
                    o["order_status"] != "Cancelled"
                    and abs(expected - o["final_amount"]) > 0.01
                ):
                    errors.append(
                        {
                            "table": "orders",
                            "id": o["id"],
                            "reason": "Tổng tiền không khớp dòng đơn và phí giao.",
                        }
                    )
                paid = sum(
                    p["paid_amount"]
                    for p in payments
                    if p["order_id"] == o["id"]
                    and p["payment_status"] in ["Success", "Refunded"]
                )
                if paid > o["final_amount"] + 0.01:
                    errors.append(
                        {
                            "table": "payments",
                            "id": o["id"],
                            "reason": "Tổng thanh toán vượt nghĩa vụ đơn.",
                        }
                    )
            checks.extend(
                ["Đối chiếu tiền đơn với dòng hàng", "Không thu vượt nghĩa vụ đơn"]
            )
            for s in u.rows("shipments"):
                if (
                    s["picked_at"]
                    and s["picked_at"] < s["created_at"]
                    or s["delivered_at"]
                    and (not s["picked_at"] or s["delivered_at"] < s["picked_at"])
                ):
                    errors.append(
                        {
                            "table": "shipments",
                            "id": s["id"],
                            "reason": "Thứ tự thời gian vận chuyển không hợp lệ.",
                        }
                    )
            checks.append("Thứ tự thời gian vận chuyển")
            index = self.extended(u, errors, checks)
        self.actor_report(index, errors, checks, job)
        return {
            "ok": not errors,
            "checks": checks,
            "errors": errors,
            "job": job,
            "scope": "Số học và quan hệ toàn DB; actor theo phạm vi job nếu được chỉ định. Các luồng đã triển khai; không thay cho việc kiểm chứng các nghiệp vụ đang khóa.",
        }

    def extended(self, u, errors, checks):
        """Independent relational checks, including nullable fields with semantic meaning."""
        from collections import Counter

        tables = {name: u.rows(name) for name in self.db.bm.tables}
        index = {name: {r["id"]: r for r in rows} for name, rows in tables.items()}

        def error(table, row, reason):
            errors.append({"table": table, "id": row["id"], "reason": reason})

        for name, table in self.db.bm.tables.items():
            for row in tables[name]:
                for fk in table.foreign_keys:
                    value = row[fk.parent.name]
                    if value is not None and value not in index[fk.column.table.name]:
                        error(name, row, f"Khóa ngoại {fk.parent.name} không tồn tại.")
        checks.append("Khóa ngoại của toàn bộ mô hình")
        defaults = Counter(
            a["customer_id"]
            for a in tables["customer_addresses"]
            if a["customer_id"] is not None and a["is_default"]
        )
        for row in tables["customers"]:
            if defaults[row["id"]] > 1:
                error("customers", row, "Khách có nhiều địa chỉ mặc định.")
        for cart in tables["cart_items"]:
            session = index["sessions"].get(cart["session_id"])
            if session and cart["customer_id"] != session["customer_id"]:
                error("cart_items", cart, "Giỏ và phiên khác khách.")
        for order in tables["orders"]:
            address = index["customer_addresses"].get(order["shipping_address_id"])
            session = index["sessions"].get(order["session_id"])
            if address and address["customer_id"] != order["customer_id"]:
                error("orders", order, "Địa chỉ không thuộc chủ đơn.")
            if session and session["customer_id"] != order["customer_id"]:
                error("orders", order, "Đơn và phiên khác khách.")
        for event in tables["page_events"]:
            session = index["sessions"].get(event["session_id"])
            if session and (
                event["event_time"] < session["started_at"]
                or (session["ended_at"] and event["event_time"] > session["ended_at"])
            ):
                error("page_events", event, "Sự kiện nằm ngoài thời gian phiên.")
            order = index["orders"].get(event["order_id"])
            if order and order["session_id"] != event["session_id"]:
                error("page_events", event, "Sự kiện mua và đơn khác phiên.")
        for item in tables["order_items"]:
            order = index["orders"].get(item["order_id"])
            product = index["products"].get(item["product_id"])
            if order and product and order["seller_id"] != product["seller_id"]:
                error("order_items", item, "Dòng đơn thuộc seller khác.")
            if (
                item["quantity"] is None
                or item["quantity"] <= 0
                or item["unit_price"] is None
                or item["unit_price"] < 0
                or item["discount_amount"] is None
                or item["discount_amount"] < 0
                or abs(
                    item["net_amount"]
                    - (item["quantity"] * item["unit_price"] - item["discount_amount"])
                )
                > 0.01
            ):
                error("order_items", item, "Tiền/số lượng dòng không hợp lệ.")
        for review in tables["product_reviews"]:
            item = index["order_items"].get(review["order_item_id"])
            order = index["orders"].get(item["order_id"]) if item else None
            if (
                not item
                or not order
                or review["product_id"] != item["product_id"]
                or review["customer_id"] != order["customer_id"]
                or not order["completed_at"]
                or review["created_at"] < order["completed_at"]
                or not 1 <= review["rating"] <= 5
            ):
                error(
                    "product_reviews",
                    review,
                    "Đánh giá sai quan hệ, thời điểm hoặc số sao.",
                )
        for order in tables["orders"]:
            paid = sum(
                r["paid_amount"]
                for r in tables["payments"]
                if r["order_id"] == order["id"]
                and r["payment_status"] in ["Success", "Refunded"]
            )
            refund = sum(
                r["amount"]
                for r in tables["refunds"]
                if r["order_id"] == order["id"] and r["refund_status"] != "Cancelled"
            )
            if refund > paid + 0.01:
                error("orders", order, "Nghĩa vụ hoàn vượt số thực thu.")
        for item in tables["order_items"]:
            returns = [
                r
                for r in tables["returns"]
                if r["order_item_id"] == item["id"] and r["status"] != "Rejected"
            ]
            if (
                sum(r["quantity"] for r in returns) > item["quantity"]
                or sum(r["refund_amount"] for r in returns) > item["net_amount"] + 0.01
            ):
                error("order_items", item, "Trả hàng vượt số lượng/tiền dòng.")
        for payout in tables["seller_payouts"]:
            rows = [
                r
                for r in tables["seller_payout_items"]
                if r["seller_payout_id"] == payout["id"]
            ]
            if rows and (
                abs(sum(r["net_amount"] for r in rows) - payout["payout_amount"]) > 0.01
                or abs(
                    payout["gross_sales"]
                    - payout["refund_amount"]
                    - payout["commission_amount"]
                    - payout["payout_amount"]
                )
                > 0.01
            ):
                error("seller_payouts", payout, "Tổng đối soát không khớp ledger.")
        checks.extend(
            [
                "Quyền sở hữu khách–địa chỉ–phiên–giỏ–đơn",
                "Tiền dòng và seller",
                "Thời gian sự kiện và liên kết mua",
                "Đánh giá sau mua",
                "Nghĩa vụ hoàn tiền và giới hạn trả",
                "Đối soát theo ledger dòng",
            ]
        )
        return index

    def actor_report(self, index, errors, checks, job=None):
        from sqlalchemy import select

        with self.db.control.connect() as conn:
            records = {
                (r.kind, r.id): r.data
                for r in conn.execute(
                    select(self.db.records).where(
                        self.db.records.c.kind.in_(["manifests", "action_results"])
                    )
                )
            }
        for (kind, key), action in records.items():
            if kind != "action_results" or (job and action.get("job") != job):
                continue
            code = action.get("code", "")
            if not code.startswith(("GST-WEB-", "CUS-WEB-")):
                continue
            for change in records.get(("manifests", key), {}).get("changes", []):
                event = change.get("after")
                if (
                    change["table"] != "page_events"
                    or not event
                    or event["id"] not in index["page_events"]
                ):
                    continue
                session = index["sessions"].get(event["session_id"])
                if session and (session["customer_id"] is None) != code.startswith(
                    "GST"
                ):
                    errors.append(
                        {
                            "table": "page_events",
                            "id": event["id"],
                            "action": code,
                            "reason": "Actor guest/registered không khớp phiên.",
                        }
                    )
        checks.append(
            "Đối chiếu actor Analytics từ nhật ký commit"
            + (" của job hiện tại" if job else " toàn lịch sử")
        )
