from datetime import datetime, timedelta
<<<<<<< Updated upstream:scripts/mock_platform/domain.py
import random
from .storage import UnitOfWork
=======

from sqlalchemy import select

from ..infrastructure.storage import UnitOfWork
>>>>>>> Stashed changes:scripts/mock_platform/engine/domain.py


class NotEligible(ValueError):
    pass


class DomainEngine:
    def __init__(self, db, uow: UnitOfWork, action, state):
        self.db, self.u, self.a, self.state = db, uow, action, state
        self.p = action.get("params", {})
        self.code = action["code"]
        self.now = action["at"]
        self.r = random.Random(action["id"])
        self.effects = []

    def choose(self, table, predicate=lambda r: True, target=None):
        target = target if target is not None else self.p.get("target")
        used_key = f"used:{self.now[:10]}:{self.code}:{table}"
        catalog_action = self.code.startswith(("SEL-", "CAT-", "MGR-"))
        used = self.getmeta(used_key, []) if catalog_action else []
        rows = [
            r
            for r in self.u.rows(table)
            if predicate(r)
            and (not target or str(r["id"]) == str(target))
            and r["id"] not in used
            and (
                not (table == "products" and self.code.startswith("SEL-"))
                or not self.p.get("actor")
                or str(r["seller_id"]) == str(self.p["actor"])
            )
        ]

        if not rows:
            raise NotEligible(f"Không có đối tượng hợp lệ trong {table}.")
        selected = self.r.choice(rows)
        if catalog_action:
            self.meta(used_key, used + [selected["id"]])
        return selected

    def touch(self, table, row, **values):
        if "updated_at" in self.db.bm.tables[table].c:
            values["updated_at"] = self.now
        return self.u.change(table, row["id"], **values)

    def meta(self, key, value):
        self.effects.append({"key": key, "value": value})

    def getmeta(self, key, default=None):
        return self.state.get(key, default)

    def saleable(self, r):
        # One table read instead of a query per seller; same rows as one().
        self.u.rows("sellers")
        s = self.u.one("sellers", r["seller_id"])
        return (
            r["is_active"]
            and s
            and s["status"] == "Active"
            and r["price"]
            and r["price"] > 0
        )

    def execute(self):
        c = self.code
        if c.startswith("SEL-") or c.startswith("CAT-") or c.startswith("MGR-"):
            return self.catalog()
        if c in ["GST-01", "CUS-01", "CUS-02", "CUS-03", "CUS-04", "SYS-03"]:
            return self.customer()
        if c in ["GST-02", "CUS-05"]:
            return self.checkout(c == "GST-02")
        if c in ["GST-03", "CUS-07", "ORD-02", "SYS-01", "SYS-02"]:
            return self.cancel()
        if c in ["CUS-06", "PAY-01", "ORD-01", "CUS-09"]:
            return self.order()
        if c.startswith(("WH-", "DSP-", "CAR-", "AUT-WH-")):
            return self.warehouse()
        if c.startswith(("MKT-", "SHOP-MKT-", "ADS-", "AUT-MKT-")):
            return self.marketing()
        if c.startswith(("GST-WEB-", "CUS-WEB-", "AUT-WEB-", "EVT-WEB-", "VIS-")):
            return self.analytics()
        if c.startswith(("FIN-", "AUT-FIN-")):
            return self.finance()
        raise NotEligible("Hành động chưa có quy tắc thực thi an toàn.")

    def catalog(self):
        c = self.code
        if c.startswith("MGR") or c in ["SEL-01", "SEL-02", "SEL-03"]:
            row = self.choose("sellers", lambda r: r["status"] == "Active")
            if c == "SEL-01":
                self.touch(
                    "sellers",
                    row,
                    shop_name=self.p.get("value")
                    or f"{row['shop_name']} · {self.a['id'][:4]}",
                )
            elif c == "SEL-02":
                self.touch(
                    "sellers",
                    row,
                    email=self.p.get("value")
                    or f"shop{row['id']}.{self.a['id'][:6]}@example.com",
                )
            elif c == "SEL-03":
                self.touch(
                    "sellers", row, province=self.p["province"], city=self.p["province"]
                )
            elif c == "MGR-01":
                self.touch("sellers", row, tier=self.p["tier"])
            elif c == "MGR-02":
                self.touch("sellers", row, status="Suspended")
                for prod in self.u.rows("products"):
                    if prod["seller_id"] == row["id"] and prod["is_active"]:
                        self.touch("products", prod, is_active=False)
                        self.meta(f"pause:{prod['id']}", "PLATFORM")
            return
        if c == "CAT-04":
            if not self.p.get("value"):
                raise NotEligible("Cần nhập tên danh mục mới.")
            row = self.choose("categories")
            self.touch("categories", row, category_name=self.p["value"])
            for prod in self.u.rows("products"):
                if prod["category_id"] == row["id"]:
                    self.touch("products", prod, category_name=self.p["value"])
            return
        if c in ["CAT-01", "CAT-02"]:
            requests = [
                (k, v)
                for k, v in self.state.items()
                if k.startswith("category_request:")
                and v["status"] == "Pending"
                and (
                    not self.p.get("target")
                    or k.split(":", 1)[1] == str(self.p["target"])
                )
            ]
            if not requests:
                raise NotEligible("Chưa có yêu cầu chuyển danh mục.")
            key, req = requests[0]
            prod = self.u.one("products", req["product"])
            if c == "CAT-01":
                cat = self.u.one("categories", req["category"])
                self.touch(
                    "products",
                    prod,
                    category_id=cat["id"],
                    category_name=cat["category_name"],
                )
            self.meta(
                key, {**req, "status": "Approved" if c == "CAT-01" else "Rejected"}
            )
            return
        prod = self.choose(
            "products",
            lambda r: (
                self.u.one("sellers", r["seller_id"])["status"] == "Active"
                and (self.code not in ["SEL-06", "CAT-03"] or r["is_active"])
                and (
                    self.code != "SEL-07"
                    or (
                        not r["is_active"]
                        and self.getmeta(f"pause:{r['id']}") == "SELLER"
                    )
                )
            ),
        )
        if c == "SEL-04":
            self.touch(
                "products",
                prod,
                name=self.p.get("value")
                or prod["name"].strip() + " · Phiên bản mô phỏng",
            )
        elif c == "SEL-05":
            self.touch(
                "products",
                prod,
                short_description=self.p.get("value")
                or f"Thông tin mô phỏng cho {prod['name']}",
            )
        elif c in ["SEL-06", "CAT-03"]:
            if not prod["is_active"]:
                raise NotEligible("Sản phẩm đã ngừng bán.")
            self.touch("products", prod, is_active=False)
            self.meta(f"pause:{prod['id']}", "SELLER" if c == "SEL-06" else "PLATFORM")
        elif c == "SEL-07":
            if prod["is_active"] or self.getmeta(f"pause:{prod['id']}") != "SELLER":
                raise NotEligible("Chỉ mở lại sản phẩm do seller tạm dừng.")
            self.touch("products", prod, is_active=True)
            self.meta(f"pause:{prod['id']}", None)
        elif c == "SEL-08":
            cat = self.u.one("categories", self.p.get("category"))
            if not cat or any(
                r["parent_id"] == cat["id"] for r in self.u.rows("categories")
            ):
                raise NotEligible("Danh mục đích phải là danh mục lá hợp lệ.")
            self.meta(
                f"category_request:{self.a['id']}",
                {"product": prod["id"], "category": cat["id"], "status": "Pending"},
            )

    def customer(self):
        c = self.code
        if c == "GST-01":
            return self.u.add(
                "customers",
                full_name=f"Khách mô phỏng {self.a['id'][:6]}",
                email=f"khach.{self.a['id']}@example.com",
                phone_number="0900000000",
                province=self.p["province"],
                city=self.p["province"],
                membership_tier="Member",
                registration_date=self.now,
                updated_at=self.now,
            )
        row = self.choose("customers")
        if c == "CUS-01":
            self.touch(
                "customers",
                row,
                full_name=self.p.get("value") or row["full_name"] + " Nguyễn",
            )
        elif c == "CUS-02":
            self.touch(
                "customers", row, province=self.p["province"], city=self.p["province"]
            )
        elif c == "SYS-03":
            self.touch("customers", row, membership_tier=self.p["new_tier"])
        elif c == "CUS-03":
            self.address(row["id"])
        elif c == "CUS-04":
            addr = self.choose(
                "customer_addresses", lambda a: a["customer_id"] == row["id"], target=""
            )
            for a in self.u.rows("customer_addresses"):
                if a["customer_id"] == row["id"]:
                    self.touch(
                        "customer_addresses", a, is_default=a["id"] == addr["id"]
                    )

    def address(self, customer=None):
        return self.u.add(
            "customer_addresses",
            customer_id=customer,
            recipient_name="Người nhận mô phỏng",
            phone="0900000000",
            address_detail=self.p.get("value") or "Địa chỉ thử nghiệm",
            ward="Phường mô phỏng",
            province=self.p.get("province", "TP. Hồ Chí Minh"),
            is_default=False,
        )

    def checkout(self, guest):
        prod = self.choose(
            "products", self.saleable, target=self.p.get("product") or ""
        )
        inv = self.choose(
            "inventory_levels",
            lambda r: (
                r["sku"] == prod["sku"]
                and r["quantity_on_hand"] - r["quantity_reserved"]
                >= int(self.p.get("quantity", 1))
            ),
            target="",
        )
        qty = int(self.p.get("quantity", 1))
        cust = None if guest else self.choose("customers")["id"]
        addr = self.address(cust)
        channel = next(
            r
            for r in self.u.rows("channels")
            if r["channel_name"] == self.p.get("channel", "Web")
        )
        amount = round(prod["price"]) * qty
        order = self.u.add(
            "orders",
            order_code="OD" + self.a["id"].replace("-", "")[:20],
            customer_id=cust,
            seller_id=prod["seller_id"],
            channel_id=channel["id"],
            order_status="Pending",
            total_gross_amount=amount,
            total_discount_amount=0,
            shipping_fee=0,
            shipping_discount_amount=0,
            final_amount=amount,
            shipping_address_id=addr["id"],
            created_at=self.now,
            updated_at=self.now,
        )
        self.u.add(
            "order_items",
            order_id=order["id"],
            line_number=1,
            product_id=prod["id"],
            quantity=qty,
            list_price=prod["original_price"],
            unit_price=prod["price"],
            discount_amount=0,
            net_amount=amount,
            item_status="Pending",
        )
        self.touch(
            "inventory_levels", inv, quantity_reserved=inv["quantity_reserved"] + qty
        )
        method = next(
            r
            for r in self.u.rows("payment_methods")
            if r["method_name"] == self.p.get("method", "COD")
        )
        self.meta(
            f"order:{order['id']}",
            {
                "warehouse": inv["warehouse_id"],
                "method": method["id"],
                "method_name": method["method_name"],
                "reserved": True,
            },
        )
        if method["method_name"] != "COD":
            self.u.add(
                "payments",
                order_id=order["id"],
                payment_method_id=method["id"],
                payment_status="Pending",
                paid_amount=0,
                transaction_time=self.now,
            )

    def cancel(self):
        # Full cancellation before pickup. Paid obligations are not discarded.
        c = self.code

        def eligible(o):
            if o["order_status"] not in ["Pending", "Processing"]:
                return False
            if c == "GST-03" and o["customer_id"] is not None:
                return False
            if c == "CUS-07" and o["customer_id"] is None:
                return False
            if any(
                s["order_code"] == o["order_code"] for s in self.u.rows("shipments")
            ):
                return False
            if any(
                p["order_id"] == o["id"] and p["payment_status"] == "Success"
                for p in self.u.rows("payments")
            ):
                return False
            if c in ["SYS-01", "SYS-02"]:
                if datetime.fromisoformat(self.now) - datetime.fromisoformat(
                    o["created_at"]
                ) < timedelta(days=self.p.get("days", 1)):
                    return False
                if (
                    c == "SYS-01"
                    and self.getmeta(f"order:{o['id']}", {}).get("method_name") == "COD"
                ):
                    return False
            return True

        order = self.choose("orders", eligible)
        self.touch("orders", order, order_status="Cancelled", cancelled_at=self.now)
        meta = self.getmeta(f"order:{order['id']}", {})
        for item in self.u.rows("order_items"):
            if item["order_id"] != order["id"]:
                continue
            self.touch("order_items", item, item_status="Cancelled")
            if meta.get("reserved"):
                prod = self.u.one("products", item["product_id"])
                inv = self.choose(
                    "inventory_levels",
                    lambda r: (
                        r["warehouse_id"] == meta["warehouse"]
                        and r["sku"] == prod["sku"]
                    ),
                    target="",
                )
                self.touch(
                    "inventory_levels",
                    inv,
                    quantity_reserved=inv["quantity_reserved"] - item["quantity"],
                )
        self.meta(f"order:{order['id']}", {**meta, "reserved": False})

    def order(self):
        c = self.code
        if c == "PAY-01":
            p = self.choose(
                "payments",
                lambda r: (
                    r["payment_status"] == "Pending"
                    and self.u.one("orders", r["order_id"])["order_status"]
                    != "Cancelled"
                ),
            )
            o = self.u.one("orders", p["order_id"])
            ok = self.r.random() * 100 < float(self.p.get("success_rate", 95))
            self.touch(
                "payments",
                p,
                payment_status="Success" if ok else "Failed",
                paid_amount=o["final_amount"] if ok else 0,
                transaction_time=self.now,
            )
            return
        if c == "CUS-06":
            o = self.choose(
                "orders",
                lambda r: (
                    r["order_status"] == "Pending"
                    and any(
                        p["order_id"] == r["id"] and p["payment_status"] == "Failed"
                        for p in self.u.rows("payments")
                    )
                    and not any(
                        p["order_id"] == r["id"]
                        and p["payment_status"] in ["Pending", "Success"]
                        for p in self.u.rows("payments")
                    )
                ),
            )
            method = next(
                r
                for r in self.u.rows("payment_methods")
                if r["method_name"] == self.p.get("method", "Momo")
            )
            if method["method_name"] == "COD":
                raise NotEligible("Không chuyển retry sang COD trong luồng trả trước.")
            self.u.add(
                "payments",
                order_id=o["id"],
                payment_method_id=method["id"],
                payment_status="Pending",
                paid_amount=0,
                transaction_time=self.now,
            )
            return
        if c == "ORD-01":

            def eligible(o):
                meta = self.getmeta(f"order:{o['id']}", {})
                return (
                    o["order_status"] == "Pending"
                    and self.u.one("sellers", o["seller_id"])["status"] == "Active"
                    and (
                        meta.get("method_name") == "COD"
                        or any(
                            p["order_id"] == o["id"]
                            and p["payment_status"] == "Success"
                            for p in self.u.rows("payments")
                        )
                    )
                )

            o = self.choose("orders", eligible)
            self.touch("orders", o, order_status="Processing")
            return
        if c == "CUS-09":
            reviewed = {r["order_item_id"] for r in self.u.rows("product_reviews")}
            i = self.choose(
                "order_items",
                lambda r: (
                    r["item_status"] == "Fulfilled"
                    and r["id"] not in reviewed
                    and self.u.one("orders", r["order_id"])["customer_id"] is not None
                ),
            )
            o = self.u.one("orders", i["order_id"])
            self.u.add(
                "product_reviews",
                order_item_id=i["id"],
                product_id=i["product_id"],
                customer_id=o["customer_id"],
                rating=self.p.get("rating", 5),
                comment=self.p.get("value") or "Đánh giá mô phỏng",
                created_at=self.now,
            )

    def warehouse(self):
        c = self.code
        if c in ["WH-01", "WH-02"]:
            prod = self.choose("products", target=self.p.get("product") or "")
            wid = self.p.get("warehouse", 1)
            if not self.u.one("warehouses", wid):
                raise NotEligible("Kho không tồn tại.")
            inv = next(
                (
                    r
                    for r in self.u.rows("inventory_levels")
                    if r["warehouse_id"] == wid and r["sku"] == prod["sku"]
                ),
                None,
            )
            if not inv:
                inv = self.u.add(
                    "inventory_levels",
                    warehouse_id=wid,
                    sku=prod["sku"],
                    quantity_on_hand=0,
                    quantity_reserved=0,
                    updated_at=self.now,
                )
            qty = int(self.p.get("quantity", 1))
            self.touch(
                "inventory_levels", inv, quantity_on_hand=inv["quantity_on_hand"] + qty
            )
            self.u.add(
                "inventory_movements",
                warehouse_id=wid,
                sku=prod["sku"],
                movement_type="Import" if c == "WH-01" else "Adjustment",
                quantity_change=qty,
                movement_date=self.now,
            )
            return
        if c == "AUT-WH-04":
            for inv in self.u.rows("inventory_levels"):
                if any(
                    r["balance_date"] == self.now[:10]
                    and r["warehouse_id"] == inv["warehouse_id"]
                    and r["sku"] == inv["sku"]
                    for r in self.u.rows("inventory_daily_balance")
                ):
                    continue
                self.u.add(
                    "inventory_daily_balance",
                    balance_date=self.now[:10],
                    warehouse_id=inv["warehouse_id"],
                    sku=inv["sku"],
                    quantity_on_hand=inv["quantity_on_hand"],
                    quantity_reserved=inv["quantity_reserved"],
                )
            return
        if c == "DSP-01":
            o = self.choose(
                "orders",
                lambda r: (
                    r["order_status"] == "Processing"
                    and not any(
                        s["order_code"] == r["order_code"]
                        for s in self.u.rows("shipments")
                    )
                ),
            )
            meta = self.getmeta(f"order:{o['id']}", {})
            if not meta.get("reserved"):
                raise NotEligible("Đơn chưa giữ hàng.")
            carrier = self.choose("carriers", target="")
            self.u.add(
                "shipments",
                order_code=o["order_code"],
                warehouse_id=meta["warehouse"],
                carrier_id=carrier["id"],
                tracking_code="TR" + self.a["id"].replace("-", "")[:20],
                shipment_status="Created",
                shipping_cost=self.p.get("amount", 30000),
                created_at=self.now,
            )
            return
        if c in ["CAR-01", "WH-03"]:
            ship = self.choose("shipments", lambda r: r["shipment_status"] == "Created")
            o = next(
                r
                for r in self.u.rows("orders")
                if r["order_code"] == ship["order_code"]
            )
            meta = self.getmeta(f"order:{o['id']}", {})
            if not meta.get("reserved"):
                raise NotEligible("Đơn không còn giữ hàng.")
            for i in self.u.rows("order_items"):
                if i["order_id"] != o["id"]:
                    continue
                prod = self.u.one("products", i["product_id"])
                inv = self.choose(
                    "inventory_levels",
                    lambda r: (
                        r["warehouse_id"] == ship["warehouse_id"]
                        and r["sku"] == prod["sku"]
                    ),
                    target="",
                )
                self.touch(
                    "inventory_levels",
                    inv,
                    quantity_on_hand=inv["quantity_on_hand"] - i["quantity"],
                    quantity_reserved=inv["quantity_reserved"] - i["quantity"],
                )
                self.u.add(
                    "inventory_movements",
                    warehouse_id=ship["warehouse_id"],
                    sku=prod["sku"],
                    movement_type="Sale",
                    quantity_change=-i["quantity"],
                    reference_code=o["order_code"],
                    movement_date=self.now,
                )
            self.meta(f"order:{o['id']}", {**meta, "reserved": False})
            self.touch("shipments", ship, shipment_status="Picked", picked_at=self.now)
            return
        if c == "CAR-02":
            ship = self.choose("shipments", lambda r: r["shipment_status"] == "Picked")
            self.touch("shipments", ship, shipment_status="In Transit")
            return
        if c == "CAR-03":
            ship = self.choose(
                "shipments", lambda r: r["shipment_status"] == "In Transit"
            )
            ok = self.r.random() * 100 < float(self.p.get("success_rate", 95))
            self.touch(
                "shipments",
                ship,
                shipment_status="Delivered" if ok else "Failed",
                **({"delivered_at": self.now} if ok else {"failed_at": self.now}),
            )
            if ok:
                o = next(
                    r
                    for r in self.u.rows("orders")
                    if r["order_code"] == ship["order_code"]
                )
                self.touch("orders", o, order_status="Completed", completed_at=self.now)
                for item in self.u.rows("order_items"):
                    if item["order_id"] == o["id"]:
                        self.touch("order_items", item, item_status="Fulfilled")
            return
        if c == "CAR-04":

            def eligible(o):
                return (
                    o["order_status"] == "Completed"
                    and self.getmeta(f"order:{o['id']}", {}).get("method_name") == "COD"
                    and not any(
                        p["order_id"] == o["id"] and p["payment_status"] == "Success"
                        for p in self.u.rows("payments")
                    )
                )

            o = self.choose("orders", eligible)
            meta = self.getmeta(f"order:{o['id']}")
            self.u.add(
                "payments",
                order_id=o["id"],
                payment_method_id=meta["method"],
                payment_status="Success",
                paid_amount=o["final_amount"],
                transaction_time=self.now,
            )
            return
        raise NotEligible(
            "Giữ/giải phóng hàng được xử lý nguyên tử từ đặt/hủy đơn; không phát lệnh độc lập."
        )

    def marketing(self):
        c = self.code
        if c == "MKT-01":
            return self.u.add(
                "marketing_campaigns",
                campaign_code="CMP" + self.a["id"][:12],
                campaign_name=self.p.get("value") or "Chiến dịch mô phỏng",
                campaign_type="Brand Awareness",
                target_channel_code="WEB",
                budget_amount=self.p.get("amount", 30000),
                start_date=self.now[:10],
                end_date=(
                    datetime.fromisoformat(self.now)
                    + timedelta(days=self.p.get("days", 7))
                )
                .date()
                .isoformat(),
            )
        if c == "MKT-02":
            campaign = self.choose("marketing_campaigns")
            spent = sum(
                x["cost_amount"]
                for x in self.u.rows("ad_spend_logs")
                if x["campaign_id"] == campaign["id"]
            )
            if self.p["amount"] < spent:
                raise NotEligible("Ngân sách thấp hơn số đã chi.")
            return self.touch(
                "marketing_campaigns", campaign, budget_amount=self.p["amount"]
            )
        if c in ["MKT-03", "MKT-04", "SHOP-MKT-01"]:
            seller = (
                self.choose("sellers", lambda r: r["status"] == "Active")
                if c == "SHOP-MKT-01"
                else None
            )
            return self.u.add(
                "promotions",
                promo_code="VC" + self.a["id"][:14],
                promo_name="Voucher mô phỏng",
                promo_type="Seller Voucher"
                if seller
                else ("Freeship Voucher" if c == "MKT-04" else "Platform Voucher"),
                seller_id=seller["id"] if seller else None,
                apply_level="Shipping" if c == "MKT-04" else "Order",
                eligibility="All",
                discount_type="Fixed Amount",
                discount_value=self.p["amount"],
                min_order_value=self.p.get("min_order", 0),
                usage_limit=self.p.get("limit", 100),
                per_customer_limit=1,
                start_date=self.now,
                end_date=(
                    datetime.fromisoformat(self.now)
                    + timedelta(days=self.p.get("days", 7))
                ).isoformat(),
            )
        if c == "ADS-01":
            campaign = self.choose(
                "marketing_campaigns",
                lambda r: (
                    r["start_date"] <= self.now[:10] <= r["end_date"]
                    and not any(
                        log["campaign_id"] == r["id"]
                        and log["log_date"] == self.now[:10]
                        for log in self.u.rows("ad_spend_logs")
                    )
                ),
            )
            spent = sum(
                x["cost_amount"]
                for x in self.u.rows("ad_spend_logs")
                if x["campaign_id"] == campaign["id"]
            )
            amount = self.p["amount"]
            clicks = int(self.p.get("quantity", 1))
            if amount + spent > campaign["budget_amount"]:
                raise NotEligible("Chi quảng cáo vượt ngân sách.")
            return self.u.add(
                "ad_spend_logs",
                campaign_id=campaign["id"],
                channel_code=campaign["target_channel_code"],
                log_date=self.now[:10],
                cost_amount=amount,
                impressions=clicks * 100,
                clicks=clicks,
            )
        if c == "AUT-MKT-03":
            self.meta(
                f"marketing_check:{self.a['id']}",
                {
                    "at": self.now,
                    "active_promotions": sum(
                        p["start_date"] <= self.now <= p["end_date"]
                        for p in self.u.rows("promotions")
                    ),
                    "active_campaigns": sum(
                        p["start_date"] <= self.now[:10] <= p["end_date"]
                        for p in self.u.rows("marketing_campaigns")
                    ),
                },
            )
            return
        raise NotEligible("Hành động chưa được bật cho luồng áp dụng voucher.")

    def has_begin_checkout(self, session_id):
        """Whether a session already has a begin_checkout event (indexed lookup)."""
        memo = self.__dict__.setdefault("_begin_checkout", {})
        if session_id not in memo:
            pe = self.db.bm.tables["page_events"]
            memo[session_id] = (
                self.u.conn.execute(
                    select(pe.c.id)
                    .where(
                        pe.c.session_id == session_id,
                        pe.c.event_type == "begin_checkout",
                    )
                    .limit(1)
                ).first()
                is not None
            )
        return memo[session_id]

    def analytics(self):
        c = self.code

        def user_matches(session):
            return (
                not c.startswith("CUS-WEB") or session["customer_id"] is not None
            ) and (not c.startswith("GST-WEB") or session["customer_id"] is None)

        if c in ["VIS-01", "GST-WEB-03", "CUS-WEB-03"]:
            session = self.choose(
                "sessions",
                lambda r: not r["ended_at"] and user_matches(r),
                target=self.p.get("target") or "",
            )
            prod = self.choose(
                "products", self.saleable, target=self.p.get("product") or ""
            )
            return self.u.add(
                "page_events",
                session_id=session["id"],
                event_type="view_product",
                product_id=prod["id"],
                event_time=self.now,
            )
        if c in ["GST-WEB-01", "CUS-WEB-01"]:
            cust = (
                self.choose("customers", target="")["id"]
                if c.startswith("CUS")
                else None
            )
            channel = next(
                r
                for r in self.u.rows("channels")
                if r["channel_name"] == self.p.get("channel", "Web")
            )
            return self.u.add(
                "sessions",
                customer_id=cust,
                channel_id=channel["id"],
                traffic_source=self.p.get("traffic", "Organic"),
                device_type=self.p.get("device", "Mobile"),
                started_at=self.now,
            )
        if c == "AUT-WEB-01":
<<<<<<< Updated upstream:scripts/mock_platform/domain.py
            s = self.choose("sessions", lambda r: not r["ended_at"])
            return self.touch("sessions", s, ended_at=self.now)
=======
            s = self.choose(
                "sessions",
                lambda r: (
                    not r["ended_at"]
                    and (
                        not self.p.get("device") or r["device_type"] == self.p["device"]
                    )
                    and (
                        not self.p.get("traffic")
                        or r["traffic_source"] == self.p["traffic"]
                    )
                    and (
                        not self.p.get("channel")
                        or self.u.one("channels", r["channel_id"])["channel_name"]
                        == self.p["channel"]
                    )
                ),
            )
            scheduled = self.getmeta("session_end:" + str(s["id"]))
            end = min(scheduled, self.now) if scheduled else self.now
            pe = self.db.bm.tables["page_events"]
            events = [
                r["event_time"]
                for r in self.u.conn.execute(
                    select(pe.c.event_time).where(pe.c.session_id == s["id"])
                ).mappings()
            ]
            events = [
                t.isoformat() if hasattr(t, "isoformat") else t for t in events
            ]
            end = max([end, s["started_at"], *events])
            return self.touch("sessions", s, ended_at=end)
>>>>>>> Stashed changes:scripts/mock_platform/engine/domain.py
        if c == "AUT-WEB-02":
            cart = self.choose(
                "cart_items",
                lambda r: (
                    r["cart_status"] == "Active"
                    and self.u.one("sessions", r["session_id"])["ended_at"] is not None
                ),
            )
            return self.touch(
                "cart_items", cart, cart_status="Abandoned", closed_at=self.now
            )
        if c.endswith("WEB-02"):
            s = self.choose(
                "sessions",
                lambda r: not r["ended_at"] and user_matches(r),
                target=self.p.get("target") or "",
            )
            return self.u.add(
                "page_events",
                session_id=s["id"],
                event_type="search",
                event_time=self.now,
            )
        if c.endswith("WEB-04"):
            s = self.choose(
                "sessions",
                lambda r: not r["ended_at"] and user_matches(r),
                target=self.p.get("target") or "",
            )
            p = self.choose(
                "products", self.saleable, target=self.p.get("product") or ""
            )
            self.u.add(
                "page_events",
                session_id=s["id"],
                product_id=p["id"],
                event_type="add_to_cart",
                event_time=self.now,
            )
            return self.u.add(
                "cart_items",
                session_id=s["id"],
                customer_id=s["customer_id"],
                product_id=p["id"],
                quantity=self.p.get("quantity", 1),
                cart_status="Active",
                added_at=self.now,
            )
        if c.endswith("WEB-05") or c.endswith("WEB-06"):
            cart = self.choose(
                "cart_items",
                lambda r: (
                    r["cart_status"] == "Active"
                    and not self.u.one("sessions", r["session_id"])["ended_at"]
<<<<<<< Updated upstream:scripts/mock_platform/domain.py
=======
                    and user_matches(self.u.one("sessions", r["session_id"]))
                    and (
                        not c.endswith("06")
                        or not self.has_begin_checkout(r["session_id"])
                    )
>>>>>>> Stashed changes:scripts/mock_platform/engine/domain.py
                ),
            )
            if c.endswith("05"):
                self.touch(
                    "cart_items", cart, cart_status="Removed", closed_at=self.now
                )
            return self.u.add(
                "page_events",
                session_id=cart["session_id"],
                product_id=cart["product_id"],
                event_type="remove_from_cart" if c.endswith("05") else "begin_checkout",
                event_time=self.now,
            )
        raise NotEligible(
            "Phụ thuộc cơ chế liên kết checkout; chưa phát sinh sự kiện giả."
        )

    def finance(self):
        c = self.code
        if c == "FIN-POL-01":
            cat = self.u.one("categories", self.p.get("category"))
            if not cat:
                raise NotEligible("Cần chọn danh mục có thật.")
            start = self.p.get("start") or self.now[:10]
            end = self.p.get("end") or None
            if end and end < start:
                raise NotEligible("Ngày kết thúc trước ngày bắt đầu.")
            for row in self.u.rows("seller_commission_rates"):
                if (
                    row["category_id"] == cat["id"]
                    and row["seller_tier"] == self.p["tier"]
                    and (not row["effective_to"] or row["effective_to"] >= start)
                    and (not end or row["effective_from"] <= end)
                ):
                    raise NotEligible("Khoảng chính sách chồng lấn.")
            return self.u.add(
                "seller_commission_rates",
                category_id=cat["id"],
                seller_tier=self.p["tier"],
                commission_rate=self.p["rate"] / 100,
                effective_from=start,
                effective_to=end,
            )
        if c == "FIN-SEL-01":
            return self.choose("seller_payouts")
        if c == "FIN-REC-02":
            payout = self.choose(
                "seller_payouts",
                lambda r: (
                    r["payout_status"] == "Pending"
                    and not self.getmeta(f"approved:{r['id']}", False)
                ),
            )
            self.meta(f"approved:{payout['id']}", True)
            return
        if c == "FIN-PAY-01":
            payout = self.choose(
                "seller_payouts",
                lambda r: (
                    r["payout_status"] == "Pending"
                    and self.getmeta(f"approved:{r['id']}", False)
                    and r["payout_amount"] > 0
                ),
            )
            return self.touch(
                "seller_payouts", payout, payout_status="Paid", paid_at=self.now
            )
        raise NotEligible(
            "Đối soát cần chốt thuộc tính và nghĩa vụ tại giao dịch; chưa tính từ catalog hiện tại."
        )
