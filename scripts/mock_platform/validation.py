from .storage import UnitOfWork


class BusinessValidator:
    """Independent arithmetic and stock checks for implemented workflows."""

    def __init__(self, db):
        self.db = db

    def report(self):
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
        return {
            "ok": not errors,
            "checks": checks,
            "errors": errors,
            "scope": "Các luồng đã triển khai; không thay cho việc kiểm chứng các nghiệp vụ đang khóa.",
        }
