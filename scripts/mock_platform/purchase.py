"""One checkout command, atomically split by seller with frozen line attributes."""

from collections import defaultdict

from .domain import NotEligible


class PurchaseWorkflow:
    def __init__(self, engine):
        self.e, self.u = engine, engine.u

    def checkout(self, guest):
        e = self.e
        linked = e.p.get("checkout_mode", "direct") == "linked"
        session = None
        if linked:
            carts = self.u.rows("cart_items")
            intents = {
                r["session_id"]
                for r in self.u.rows("page_events")
                if r["event_type"] == "begin_checkout"
            }
            consumed = {r["cart_item_id"] for r in self.u.rows("checkout_lines")}
            candidates = [
                s
                for s in self.u.rows("sessions")
                if (
                    (s["customer_id"] is None) == guest
                    and not s["ended_at"]
                    and s["id"] in intents
                    and (not e.p.get("session") or str(s["id"]) == str(e.p["session"]))
                    and (
                        not e.p.get("target")
                        or str(s["customer_id"]) == str(e.p["target"])
                    )
                    and any(
                        c["session_id"] == s["id"]
                        and c["cart_status"] == "Active"
                        and c["id"] not in consumed
                        for c in carts
                    )
                )
            ]
            if not candidates:
                raise NotEligible(
                    "Chưa có phiên đúng nhóm với giỏ và yêu cầu checkout chưa xử lý."
                )
            session = e.r.choice(candidates)
            selected = [
                c
                for c in carts
                if c["session_id"] == session["id"]
                and c["cart_status"] == "Active"
                and c["id"] not in consumed
            ]
            lines = [
                (self.u.one("products", c["product_id"]), c["quantity"], c)
                for c in selected
            ]
            cust = session["customer_id"]
        else:
            qty = int(e.p.get("quantity", 1))
            prod = e.choose(
                "products",
                lambda p: (
                    e.saleable(p)
                    and any(
                        inv["sku"] == p["sku"]
                        and inv["quantity_on_hand"] - inv["quantity_reserved"] >= qty
                        and (
                            not e.p.get("warehouse")
                            or inv["warehouse_id"] == e.p["warehouse"]
                        )
                        for inv in self.u.rows("inventory_levels")
                    )
                ),
                target=e.p.get("product") or "",
            )
            lines = [(prod, qty, None)]
            cust = None if guest else e.choose("customers")["id"]
        if any(not p or not e.saleable(p) or qty <= 0 for p, qty, _ in lines):
            raise NotEligible("Giỏ có sản phẩm không đủ điều kiện bán.")
        method = next(
            (
                r
                for r in self.u.rows("payment_methods")
                if r["method_name"] == e.p.get("method", "COD")
            ),
            None,
        )
        channel = (
            self.u.one("channels", session["channel_id"])
            if session
            else next(
                (
                    r
                    for r in self.u.rows("channels")
                    if r["channel_name"] == e.p.get("channel", "Web")
                ),
                None,
            )
        )
        if not method or not channel:
            raise NotEligible(
                "Chưa có kênh hoặc phương thức thanh toán trong dữ liệu nền."
            )
        address = next(
            (
                r
                for r in self.u.rows("customer_addresses")
                if cust is not None and r["customer_id"] == cust and r["is_default"]
            ),
            None,
        ) or e.address(cust)
        checkout = self.u.add(
            "checkouts",
            checkout_code="CK" + e.a["id"],
            session_id=session["id"] if session else None,
            customer_id=cust,
            created_at=e.now,
        )
        grouped = defaultdict(list)
        for line in lines:
            grouped[line[0]["seller_id"]].append(line)
        for index, (seller, items) in enumerate(sorted(grouped.items())):
            needed = defaultdict(int)
            for product, qty, _ in items:
                needed[product["sku"]] += qty
            warehouses = [
                w
                for w in self.u.rows("warehouses")
                if (not e.p.get("warehouse") or w["id"] == e.p["warehouse"])
                and all(
                    any(
                        inv["warehouse_id"] == w["id"]
                        and inv["sku"] == sku
                        and inv["quantity_on_hand"] - inv["quantity_reserved"] >= qty
                        for inv in self.u.rows("inventory_levels")
                    )
                    for sku, qty in needed.items()
                )
            ]
            if not warehouses:
                raise NotEligible(
                    "Checkout nguyên tử bị từ chối: không có một kho đủ toàn bộ dòng của shop."
                )
            warehouse = e.r.choice(warehouses)
            gross = round(sum(p["price"] * qty for p, qty, _ in items), 2)
            shipping = e.p.get("shipping_fee", 0)
            order = self.u.add(
                "orders",
                checkout_id=checkout["id"],
                order_code="OD" + e.a["id"][:20] + f"-{index}",
                customer_id=cust,
                seller_id=seller,
                channel_id=channel["id"],
                session_id=session["id"] if session else None,
                campaign_id=session.get("campaign_id") if session else None,
                order_status="Pending",
                total_gross_amount=gross,
                total_discount_amount=0,
                shipping_fee=shipping,
                shipping_discount_amount=0,
                final_amount=gross + shipping,
                shipping_address_id=address["id"],
                created_at=e.now,
                updated_at=e.now,
            )
            for number, (product, qty, cart) in enumerate(items, 1):
                tier = self.u.one("sellers", seller)["tier"]
                policy = next(
                    (
                        r
                        for r in self.u.rows("seller_commission_rates")
                        if r["category_id"] == product["category_id"]
                        and r["seller_tier"] == tier
                        and r["effective_from"] <= e.now[:10]
                        and (not r["effective_to"] or r["effective_to"] >= e.now[:10])
                    ),
                    None,
                )
                item = self.u.add(
                    "order_items",
                    order_id=order["id"],
                    line_number=number,
                    product_id=product["id"],
                    quantity=qty,
                    list_price=product["original_price"],
                    unit_price=product["price"],
                    discount_amount=0,
                    net_amount=round(product["price"] * qty, 2),
                    item_status="Pending",
                    commission_rate=policy["commission_rate"] if policy else None,
                    commission_category_id=product["category_id"],
                    commission_seller_tier=tier,
                )
                if cart:
                    self.u.add(
                        "checkout_lines",
                        checkout_id=checkout["id"],
                        cart_item_id=cart["id"],
                        order_item_id=item["id"],
                    )
                    e.touch(
                        "cart_items", cart, cart_status="Converted", closed_at=e.now
                    )
            for sku, qty in needed.items():
                inv = next(
                    r
                    for r in self.u.rows("inventory_levels")
                    if r["warehouse_id"] == warehouse["id"] and r["sku"] == sku
                )
                e.touch(
                    "inventory_levels",
                    inv,
                    quantity_reserved=inv["quantity_reserved"] + qty,
                )
            e.meta(
                f"order:{order['id']}",
                {
                    "warehouse": warehouse["id"],
                    "method": method["id"],
                    "method_name": method["method_name"],
                    "reserved": True,
                    "policy": dict(e.policy),
                    "schedule": dict(e.a.get("schedule", {})),
                },
            )
            from .benefits import PromotionWorkflow

            PromotionWorkflow(e).apply(order)
            order = self.u.one("orders", order["id"])
            if method["method_name"] != "COD":
                self.u.add(
                    "payments",
                    order_id=order["id"],
                    payment_method_id=method["id"],
                    payment_status="Pending",
                    paid_amount=0,
                    transaction_time=e.now,
                )
            if linked:
                # Metric definition: purchase = accepted order, not successful payment.
                self.u.add(
                    "page_events",
                    session_id=session["id"],
                    order_id=order["id"],
                    event_type="purchase",
                    event_time=e.now,
                )
