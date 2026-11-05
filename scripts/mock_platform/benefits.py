"""One merchandise voucher and one shipping voucher per order, with usage ledger."""

from decimal import Decimal, ROUND_DOWN

from .domain import NotEligible


class PromotionWorkflow:
    def __init__(self, engine):
        self.e, self.u = engine, engine.u

    def apply(self, order):
        e = self.e
        if e.p.get("voucher_mode", "none") == "none":
            return
        # No persistent identity for direct guest: do not pretend to enforce per-customer caps.
        if order["customer_id"] is None:
            raise NotEligible(
                "Voucher có giới hạn theo khách yêu cầu tài khoản; không tự tạo khách cho guest."
            )
        total = 0
        shipping_discount = 0
        for shipping in [False, True]:
            target = e.p.get("shipping_voucher" if shipping else "order_voucher")
            eligible = []
            for p in self.u.rows("promotions"):
                uses = [
                    u
                    for u in self.u.rows("promotion_usages")
                    if u["promotion_id"] == p["id"] and u["usage_status"] != "Released"
                ]
                if (
                    (p["apply_level"] == "Shipping") == shipping
                    and p["start_date"] <= e.now <= p["end_date"]
                    and p["discount_type"] == "Fixed Amount"
                    and p["product_id"] is None
                    and p["eligibility"] == "All"
                    and p["seller_id"] in [None, order["seller_id"]]
                    and order["total_gross_amount"] >= p["min_order_value"]
                    and (not p["usage_limit"] or len(uses) < p["usage_limit"])
                    and (
                        not p["per_customer_limit"]
                        or sum(u["customer_id"] == order["customer_id"] for u in uses)
                        < p["per_customer_limit"]
                    )
                    and (not target or str(p["id"]) == str(target))
                ):
                    eligible.append(p)
            if not eligible:
                if target:
                    raise NotEligible(
                        "Voucher chỉ định không đủ điều kiện hoặc đã hết lượt."
                    )
                continue
            base = order["shipping_fee"] if shipping else order["total_gross_amount"]
            promo = max(
                eligible,
                key=lambda p: (
                    min(
                        p["discount_value"],
                        p["max_discount_amount"] or p["discount_value"],
                        base,
                    ),
                    -p["id"],
                ),
            )
            discount = round(
                min(
                    promo["discount_value"],
                    promo["max_discount_amount"] or promo["discount_value"],
                    base,
                ),
                2,
            )
            if discount <= 0:
                continue
            self.u.add(
                "promotion_usages",
                promotion_id=promo["id"],
                order_id=order["id"],
                customer_id=order["customer_id"],
                discount_amount=discount,
                usage_status="Used",
                created_at=e.now,
            )
            if shipping:
                shipping_discount = discount
                e.touch("orders", order, shipping_promotion_id=promo["id"])
            else:
                total = discount
                lines = [
                    r
                    for r in self.u.rows("order_items")
                    if r["order_id"] == order["id"]
                ]
                left = Decimal(str(discount))
                gross = Decimal(str(base))
                for index, line in enumerate(lines):
                    share = (
                        left
                        if index == len(lines) - 1
                        else (
                            Decimal(str(discount))
                            * Decimal(str(line["net_amount"]))
                            / gross
                        ).quantize(Decimal(".01"), rounding=ROUND_DOWN)
                    )
                    left -= share
                    self.u.add(
                        "order_item_promotions",
                        order_item_id=line["id"],
                        promotion_id=promo["id"],
                        applied_discount_amount=float(share),
                        funded_by="Seller"
                        if promo["promo_type"] == "Seller Voucher"
                        else "Platform",
                    )
                    e.touch(
                        "order_items",
                        line,
                        discount_amount=float(share),
                        net_amount=round(line["net_amount"] - float(share), 2),
                    )
        e.touch(
            "orders",
            order,
            total_discount_amount=total,
            shipping_discount_amount=shipping_discount,
            final_amount=round(
                order["total_gross_amount"]
                - total
                + order["shipping_fee"]
                - shipping_discount,
                2,
            ),
        )

    def release(self, order):
        for row in self.u.rows("promotion_usages"):
            if row["order_id"] == order["id"] and row["usage_status"] != "Released":
                self.e.touch(
                    "promotion_usages",
                    row,
                    usage_status="Released",
                    released_at=self.e.now,
                )
