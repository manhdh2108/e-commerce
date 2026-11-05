"""Return receipt, refund obligation and failed-delivery closure are separate steps."""

from datetime import datetime, timedelta

from .domain import NotEligible


class AfterSalesWorkflow:
    def __init__(self, engine):
        self.e, self.u = engine, engine.u

    def paid(self, order):
        return sum(
            p["paid_amount"]
            for p in self.u.rows("payments")
            if p["order_id"] == order["id"]
            and p["payment_status"] in ["Success", "Refunded"]
        )

    def refund(self, order, amount, reason, return_id=None):
        if amount <= 0:
            return
        obligations = sum(
            r["amount"]
            for r in self.u.rows("refunds")
            if r["order_id"] == order["id"] and r["refund_status"] != "Cancelled"
        )
        if round(obligations + amount - self.paid(order), 2) > 0:
            raise NotEligible("Nghĩa vụ hoàn vượt số thực thu còn lại.")
        self.u.add(
            "refunds",
            order_id=order["id"],
            return_id=return_id,
            amount=round(amount, 2),
            reason=reason,
            refund_status="Pending",
            requested_at=self.e.now,
        )

    def execute(self):
        e, c = self.e, self.e.code
        if c in ["GST-04", "CUS-08"]:
            qty = int(e.p.get("quantity", 1))

            def eligible(line):
                order = self.u.one("orders", line["order_id"])
                returned = sum(
                    r["quantity"]
                    for r in self.u.rows("returns")
                    if r["order_item_id"] == line["id"] and r["status"] != "Rejected"
                )
                return (
                    order["order_status"] == "Completed"
                    and (order["customer_id"] is None) == (c == "GST-04")
                    and datetime.fromisoformat(e.now)
                    <= datetime.fromisoformat(order["completed_at"])
                    + timedelta(
                        days=e.getmeta(f"order:{order['id']}", {}).get(
                            "policy", e.policy
                        )["return_window_days"]
                    )
                    and self.paid(order) >= order["final_amount"]
                    and qty <= line["quantity"] - returned
                )

            line = e.choose("order_items", eligible)
            order = self.u.one("orders", line["order_id"])
            # Final return receives the rounding remainder of the immutable line net.
            previous = [
                r
                for r in self.u.rows("returns")
                if r["order_item_id"] == line["id"] and r["status"] != "Rejected"
            ]
            remainder_qty = line["quantity"] - sum(r["quantity"] for r in previous)
            amount = (
                round(line["net_amount"] - sum(r["refund_amount"] for r in previous), 2)
                if qty == remainder_qty
                else round(line["net_amount"] * qty / line["quantity"], 2)
            )
            return self.u.add(
                "returns",
                order_item_id=line["id"],
                quantity=qty,
                return_reason=e.p["reason"],
                refund_amount=amount,
                status="Requested",
                requested_at=e.now,
                warehouse_id=e.getmeta(f"order:{order['id']}")["warehouse"],
            )
        if c in ["SUP-01", "SUP-02"]:
            row = e.choose("returns", lambda r: r["status"] == "Requested")
            return e.touch(
                "returns",
                row,
                status="Approved" if c == "SUP-01" else "Rejected",
                approved_at=e.now if c == "SUP-01" else None,
                decision_reason=e.p.get("reason") if c == "SUP-02" else None,
            )
        if c == "WH-04":
            row = e.choose("returns", lambda r: r["status"] == "Approved")
            line = self.u.one("order_items", row["order_item_id"])
            product = self.u.one("products", line["product_id"])
            inv = next(
                r
                for r in self.u.rows("inventory_levels")
                if r["warehouse_id"] == row["warehouse_id"]
                and r["sku"] == product["sku"]
            )
            e.touch(
                "inventory_levels",
                inv,
                quantity_on_hand=inv["quantity_on_hand"] + row["quantity"],
            )
            self.u.add(
                "inventory_movements",
                warehouse_id=inv["warehouse_id"],
                sku=inv["sku"],
                movement_type="Return",
                quantity_change=row["quantity"],
                reference_code=f"RETURN:{row['id']}",
                movement_date=e.now,
            )
            e.touch(
                "returns",
                row,
                status="Received" if row["refund_amount"] else "Refunded",
                received_at=e.now,
                refunded_at=None if row["refund_amount"] else e.now,
            )
            return self.refund(
                self.u.one("orders", line["order_id"]),
                row["refund_amount"],
                "Return",
                row["id"],
            )
        if c == "PAY-02":
            row = e.choose("refunds", lambda r: r["refund_status"] == "Pending")
            e.touch("refunds", row, refund_status="Completed", completed_at=e.now)
            if row["return_id"]:
                returned = self.u.one("returns", row["return_id"])
                e.touch("returns", returned, status="Refunded", refunded_at=e.now)
            return
        if c in ["CAR-05", "CAR-06"]:

            def eligible(s):
                order = next(
                    r
                    for r in self.u.rows("orders")
                    if r["order_code"] == s["order_code"]
                )
                policy = e.getmeta(f"order:{order['id']}", {}).get("policy", e.policy)
                attempts = sum(
                    a["shipment_id"] == s["id"]
                    for a in self.u.rows("delivery_attempts")
                )
                return s["shipment_status"] == "Failed" and (
                    (
                        c == "CAR-05"
                        and (
                            e.p.get("return_policy") != "attempts_exhausted"
                            or attempts >= policy["max_delivery_attempts"]
                        )
                    )
                    or (c == "CAR-06" and attempts < policy["max_delivery_attempts"])
                )

            ship = e.choose("shipments", eligible)
            if c == "CAR-06":
                return e.touch(
                    "shipments",
                    ship,
                    shipment_status="In Transit",
                    in_transit_at=e.now,
                    failed_at=None,
                )
            order = next(
                r
                for r in self.u.rows("orders")
                if r["order_code"] == ship["order_code"]
            )
            for line in self.u.rows("order_items"):
                if line["order_id"] != order["id"]:
                    continue
                product = self.u.one("products", line["product_id"])
                inv = next(
                    r
                    for r in self.u.rows("inventory_levels")
                    if r["warehouse_id"] == ship["warehouse_id"]
                    and r["sku"] == product["sku"]
                )
                e.touch(
                    "inventory_levels",
                    inv,
                    quantity_on_hand=inv["quantity_on_hand"] + line["quantity"],
                )
                self.u.add(
                    "inventory_movements",
                    warehouse_id=inv["warehouse_id"],
                    sku=inv["sku"],
                    movement_type="Return",
                    quantity_change=line["quantity"],
                    reference_code="RTO:" + order["order_code"],
                    movement_date=e.now,
                )
                e.touch("order_items", line, item_status="Cancelled")
            e.touch("shipments", ship, shipment_status="Returned", returned_at=e.now)
            e.touch(
                "orders",
                order,
                order_status="Cancelled",
                cancelled_at=e.now,
                cancellation_reason="Giao thất bại, đã nhận hàng về kho",
            )
            from .benefits import PromotionWorkflow

            PromotionWorkflow(e).release(order)
            return self.refund(order, self.paid(order), "Failed delivery")
        raise NotEligible("Chưa hỗ trợ hành động sau bán này.")
