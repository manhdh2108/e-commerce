"""Read-only audit of current OLTP and Control DB; safe during a running job.

Usage: python -m scripts.mock_platform.diagnostics.audit --output docs/mock-design/audit-results.json
No initialization, pause, recovery, migration or business writes are performed.
"""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, select, text

from ..application.service import ACTIONS, PlatformService, stamp
from ..infrastructure.storage import clean
from ..resources import RESOURCE_ROOT


def money(value):
    return Decimal(str(value or 0))


class ReadOnlyAudit:
    def __init__(self, service=None):
        self.s = service or PlatformService()
        self.db = self.s.db
        self.checks = []
        self.findings = {}

    def check(self, name, bad):
        rows = list(bad)
        self.checks.append(
            {"check": name, "violations": len(rows), "examples": clean(rows[:8])}
        )

    def run(self):
        started = stamp()
        # Anchor the business snapshot first. Control may include later work; this
        # is explicitly accounted for when comparing history and checkpoints.
        with self.db.business.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as c:
            with c.begin():
                c.exec_driver_sql("SET TRANSACTION READ ONLY")
                inspector = inspect(c)
                business_tables = inspector.get_table_names()
                business = {}
                physical = {}
                quote = c.dialect.identifier_preparer.quote
                for n, t in self.db.bm.tables.items():
                    present = n in business_tables
                    business[n] = (
                        [
                            dict.fromkeys(t.c.keys()) | clean(dict(r))
                            for r in c.execute(
                                text("SELECT * FROM " + quote(n))
                            ).mappings()
                        ]
                        if present
                        else []
                    )
                    physical[n] = {
                        "fks": inspector.get_foreign_keys(n) if present else [],
                        "unique": inspector.get_unique_constraints(n)
                        if present
                        else [],
                        "nullable": [
                            x["name"] for x in inspector.get_columns(n) if x["nullable"]
                        ]
                        if present
                        else list(t.c.keys()),
                    }
        with self.db.control.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as c:
            with c.begin():
                c.exec_driver_sql("SET TRANSACTION READ ONLY")
                control = defaultdict(dict)
                for r in c.execute(select(self.db.records)):
                    control[r.kind][r.id] = r.data
                control_tables = inspect(c).get_table_names()
        self.b, self.c = business, control
        self.idx = {n: {r["id"]: r for r in rows} for n, rows in business.items()}
        self.active = [
            {"id": k, **v}
            for k, v in control["jobs"].items()
            if v["status"] in ["RUNNING", "QUEUED", "PAUSING"]
        ]
        self.last = control["checkpoint"].get("main", {}).get("last_day")
        max_balance = max(
            (r["balance_date"] for r in business["inventory_daily_balance"]),
            default=None,
        )
        self.closed = min(self.last, max_balance) if self.last and max_balance else None
        self.structure(physical)
        self.catalog()
        self.orders()
        self.inventory()
        self.analytics()
        self.marketing_finance()
        self.control_checks()
        self.journal()
        nullable = json.loads(
            (RESOURCE_ROOT / "business_schema.json").read_text()
        )
        self.findings["null_fields"] = {
            n: {
                col: sum(r[col] is None for r in rows)
                for col in self.db.bm.tables[n].c.keys()
                if rows and any(r[col] is None for r in rows)
            }
            for n, rows in business.items()
        }
        self.findings["metadata_required_but_nullable"] = {
            n: [
                f["name"]
                for f in fields
                if not f["nullable"] and f["name"] in physical[n]["nullable"]
            ]
            for n, fields in nullable.items()
        }
        self.findings["profiles"] = {
            "distinct_customer_phones": len(
                {r["phone_number"] for r in business["customers"]}
            ),
            "distinct_address_details": len(
                {r["address_detail"] for r in business["customer_addresses"]}
            ),
            "customers_with_address_without_default": sum(
                any(a["customer_id"] == r["id"] for a in business["customer_addresses"])
                and not any(
                    a["customer_id"] == r["id"] and a["is_default"]
                    for a in business["customer_addresses"]
                )
                for r in business["customers"]
            ),
            "review_ratings": dict(
                Counter(r["rating"] for r in business["product_reviews"])
            ),
            "product_crawl_after_mock_created": sum(
                r["crawl_date"] > r["created_at"][:10]
                for r in business["products"]
                if r["crawl_date"] and r["created_at"]
            ),
        }
        return {
            "started_at": started,
            "finished_at": stamp(),
            "business_snapshot_first": True,
            "read_only": True,
            "target": self.db.business.url.render_as_string(hide_password=True),
            "last_day_in_control": self.last,
            "checked_closed_through": self.closed,
            "active_jobs_at_control_snapshot": self.active,
            "counts": {n: len(r) for n, r in business.items()},
            "business_tables": business_tables,
            "control_tables": control_tables,
            "checks": self.checks,
            "findings": self.findings,
        }

    def structure(self, physical):
        for n, spec in physical.items():
            for fk in spec["fks"]:
                fields, refs, target = (
                    fk["constrained_columns"],
                    fk["referred_columns"],
                    fk["referred_table"],
                )
                targets = {tuple(r[k] for k in refs) for r in self.b[target]}
                self.check(
                    "FK " + n + "." + ",".join(fields),
                    [
                        r["id"]
                        for r in self.b[n]
                        if all(r[k] is not None for k in fields)
                        and tuple(r[k] for k in fields) not in targets
                    ],
                )
            for uq in spec["unique"]:
                cols = uq["column_names"]
                counts = Counter(
                    tuple(r[k] for k in cols)
                    for r in self.b[n]
                    if all(r[k] is not None for k in cols)
                )
                self.check(
                    "UNIQUE " + n + "." + ",".join(cols),
                    [list(k) for k, v in counts.items() if v > 1],
                )
        for table, field, target, key in [
            ("shipments", "order_code", "orders", "order_code"),
            ("inventory_levels", "sku", "products", "sku"),
            ("inventory_movements", "sku", "products", "sku"),
            ("inventory_daily_balance", "sku", "products", "sku"),
        ]:
            valid = {r[key] for r in self.b[target]}
            self.check(
                "Logical reference " + table + "." + field,
                [r["id"] for r in self.b[table] if r[field] not in valid],
            )
        self.findings["physical_fk_count"] = sum(
            len(s["fks"]) for s in physical.values()
        )
        self.findings["non_pk_nullable_columns"] = sum(
            len(s["nullable"]) for s in physical.values()
        )

    def catalog(self):
        self.check(
            "Product identity / price / active seller",
            [
                r["id"]
                for r in self.b["products"]
                if not r["sku"]
                or money(r["price"]) <= 0
                or (
                    r["is_active"]
                    and self.idx["sellers"][r["seller_id"]]["status"] != "Active"
                )
            ],
        )
        self.check(
            "Category denormalized name",
            [
                r["id"]
                for r in self.b["products"]
                if r["category_name"]
                != self.idx["categories"][r["category_id"]]["category_name"]
            ],
        )
        cycles = []
        for r in self.b["categories"]:
            seen = set()
            current = r
            while current:
                if current["id"] in seen:
                    cycles.append(r["id"])
                    break
                seen.add(current["id"])
                current = self.idx["categories"].get(current["parent_id"])
        self.check("Category cycles", cycles)
        with sqlite3.connect(
            Path(self.c["settings"]["main"]["source"]).as_uri() + "?mode=ro", uri=True
        ) as c:
            c.row_factory = sqlite3.Row
            c.execute("BEGIN")
            source = {r["id"]: dict(r) for r in c.execute("SELECT * FROM products")}
            self.findings["source_tables"] = [
                r[0]
                for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
        original = {}
        for jid, job in self.c["jobs"].items():
            if job["kind"] == "sync" and not job.get("archived"):
                preview = self.c["sync_previews"].get(job["payload"]["preview"], {})
                for prod in preview.get("products", []):
                    original.setdefault(prod["id"], prod)
        identity = []
        price = []
        for p in self.b["products"]:
            orig = original.get(p["id"])
            if not orig or (
                str(p["sku"]),
                p["seller_id"],
                str(p["seller_product_id"]),
            ) != (
                str(orig["sku"]),
                orig["seller_id"],
                str(orig.get("seller_product_id")),
            ):
                identity.append(p["id"])
            if orig and money(p["price"]) != money(orig["price"]):
                price.append(p["id"])
        self.check("Tiki original ID/SKU/seller/offer retained", identity)
        self.check("First-sync selling price retained", price)
        self.findings["source_comparison"] = {
            "source_products": len(source),
            "new_source_ids": len(set(source) - set(self.idx["products"])),
            "target_ids_missing_from_current_source": len(
                set(self.idx["products"]) - set(source)
            ),
            "prices_different_from_current_source": sum(
                p["id"] in source
                and money(p["price"]) != money(source[p["id"]]["price"])
                for p in self.b["products"]
            ),
            "provenance_records": sum(
                k.startswith("provenance:") for k in self.c["runtime"]
            ),
        }

    def orders(self):
        b = self.b
        i = self.idx
        self.lines = defaultdict(list)
        self.pay = defaultdict(list)
        self.ships = {}
        for r in b["order_items"]:
            self.lines[r["order_id"]].append(r)
        for r in b["payments"]:
            self.pay[r["order_id"]].append(r)
        for r in b["shipments"]:
            self.ships[r["order_code"]] = r
        badmoney = []
        badline = []
        badowner = []
        badstates = []
        badpaid = []
        badtime = []
        badshipping = []
        for r in b["order_items"]:
            o = i["orders"][r["order_id"]]
            p = i["products"][r["product_id"]]
            if (
                r["quantity"] <= 0
                or money(r["unit_price"]) < 0
                or money(r["discount_amount"]) < 0
                or abs(
                    money(r["net_amount"])
                    - (
                        money(r["unit_price"]) * r["quantity"]
                        - money(r["discount_amount"])
                    )
                )
                > Decimal(".01")
            ):
                badline.append(r["id"])
            if o["seller_id"] != p["seller_id"]:
                badowner.append({"item": r["id"], "reason": "seller"})
        for o in b["orders"]:
            lines = self.lines[o["id"]]
            ship = self.ships.get(o["order_code"])
            payments = self.pay[o["id"]]
            gross = sum(money(x["unit_price"]) * x["quantity"] for x in lines)
            discount = sum(money(x["discount_amount"]) for x in lines)
            if not lines or any(
                abs(a - bb) > Decimal(".01")
                for a, bb in [
                    (gross, money(o["total_gross_amount"])),
                    (discount, money(o["total_discount_amount"])),
                    (
                        gross
                        - discount
                        + money(o["shipping_fee"])
                        - money(o["shipping_discount_amount"]),
                        money(o["final_amount"]),
                    ),
                ]
            ):
                badmoney.append(o["id"])
            addr = i["customer_addresses"][o["shipping_address_id"]]
            if addr["customer_id"] != o["customer_id"]:
                badowner.append({"order": o["id"], "reason": "address owner"})
            success = sum(
                money(p["paid_amount"])
                for p in payments
                if p["payment_status"] == "Success"
            )
            if (
                success > money(o["final_amount"]) + Decimal(".01")
                or (
                    o["order_status"] == "Completed"
                    and self.closed
                    and o.get("completed_at")
                    and o["completed_at"][:10] <= self.closed
                    and success != money(o["final_amount"])
                )
                or (
                    o["order_status"] == "Cancelled"
                    and success
                    > sum(
                        money(r["amount"])
                        for r in b["refunds"]
                        if r["order_id"] == o["id"]
                        and r["refund_status"] != "Cancelled"
                    )
                )
            ):
                badpaid.append(o["id"])
            if o["order_status"] == "Completed" and (
                not ship
                or ship["shipment_status"] != "Delivered"
                or not o["completed_at"]
                or any(x["item_status"] != "Fulfilled" for x in lines)
            ):
                badstates.append(o["id"])
            if o["order_status"] == "Cancelled" and (
                (ship and ship["shipment_status"] not in ["Returned", "Cancelled"])
                or not o["cancelled_at"]
                or any(x["item_status"] != "Cancelled" for x in lines)
            ):
                badstates.append(o["id"])
            for p in payments:
                if p["transaction_time"] < o["created_at"] or (
                    p["payment_status"] == "Failed" and money(p["paid_amount"]) != 0
                ):
                    badtime.append({"payment": p["id"]})
                if (
                    p["payment_status"] == "Success"
                    and i["payment_methods"][p["payment_method_id"]]["method_name"]
                    == "COD"
                    and (
                        not ship
                        or not ship["delivered_at"]
                        or p["transaction_time"] < ship["delivered_at"]
                    )
                ):
                    badtime.append({"cod": p["id"]})
            if (
                o["customer_id"]
                and i["customers"][o["customer_id"]]["registration_date"]
                > o["created_at"]
            ):
                badtime.append({"order_before_registration": o["id"]})
        for s in b["shipments"]:
            o = next(o for o in b["orders"] if o["order_code"] == s["order_code"])
            if (
                s["created_at"] < o["created_at"]
                or (s["picked_at"] and s["picked_at"] < s["created_at"])
                or (
                    s["delivered_at"]
                    and (not s["picked_at"] or s["delivered_at"] < s["picked_at"])
                )
            ):
                badshipping.append(s["id"])
            if s["shipment_status"] == "Delivered" and (
                o["order_status"] != "Completed"
                or o["completed_at"] != s["delivered_at"]
            ):
                badshipping.append(s["id"])
        self.check("Order gross/discount/final arithmetic", badmoney)
        self.check("Line arithmetic / quantity", badline)
        self.check("Order seller and address ownership", badowner)
        self.check("Order state agrees with lines/shipment", badstates)
        self.check(
            "Paid amount equals due completed obligation / paid cancellations have refund ledger",
            badpaid,
        )
        self.check(
            "Payment chronology, COD after delivery, customer exists before purchase",
            badtime,
        )
        self.check("Shipping chronology and completion timestamp", badshipping)
        self.check(
            "Review owner/product/fulfilled/after delivery",
            [
                r["id"]
                for r in b["product_reviews"]
                if r["product_id"] != i["order_items"][r["order_item_id"]]["product_id"]
                or r["customer_id"]
                != i["orders"][i["order_items"][r["order_item_id"]]["order_id"]][
                    "customer_id"
                ]
                or i["order_items"][r["order_item_id"]]["item_status"] != "Fulfilled"
                or not 1 <= r["rating"] <= 5
                or r["created_at"]
                < i["orders"][i["order_items"][r["order_item_id"]]["order_id"]][
                    "completed_at"
                ]
            ],
        )
        self.findings["states"] = {
            n: dict(Counter(r[col] for r in b[n]))
            for n, col in [
                ("orders", "order_status"),
                ("payments", "payment_status"),
                ("shipments", "shipment_status"),
                ("cart_items", "cart_status"),
            ]
        }
        self.findings["order_shape"] = {
            "multi_line_orders": sum(len(x) > 1 for x in self.lines.values()),
            "quantity_distribution": dict(
                Counter(r["quantity"] for r in b["order_items"])
            ),
            "completed_same_day": sum(
                bool(o["completed_at"])
                and o["completed_at"][:10] == o["created_at"][:10]
                for o in b["orders"]
            ),
            "zero_shipping_fee": sum(
                money(o["shipping_fee"]) == 0 for o in b["orders"]
            ),
            "zero_order_discount": sum(
                money(o["total_discount_amount"]) == 0 for o in b["orders"]
            ),
        }

    def inventory(self):
        b = self.b
        mov = defaultdict(int)
        reserved = defaultdict(int)
        sale = Counter()
        expected_sale = Counter()
        for m in b["inventory_movements"]:
            mov[(m["warehouse_id"], m["sku"])] += m["quantity_change"]
            if m["movement_type"] == "Sale":
                sale[(m["reference_code"], m["warehouse_id"], m["sku"])] += -m[
                    "quantity_change"
                ]
        for o in b["orders"]:
            ship = self.ships.get(o["order_code"])
            meta = self.c["runtime"].get("order:" + str(o["id"]), {})
            wid = ship["warehouse_id"] if ship else meta.get("warehouse")
            for line in self.lines[o["id"]]:
                sku = self.idx["products"][line["product_id"]]["sku"]
                if ship and ship["picked_at"]:
                    expected_sale[(o["order_code"], wid, sku)] += line["quantity"]
                elif o["order_status"] != "Cancelled":
                    reserved[(wid, sku)] += line["quantity"]
        self.check(
            "Stock agrees with complete movement ledger",
            [
                r["id"]
                for r in b["inventory_levels"]
                if mov[(r["warehouse_id"], r["sku"])] != r["quantity_on_hand"]
            ],
        )
        self.check(
            "Reserved stock bounds",
            [
                r["id"]
                for r in b["inventory_levels"]
                if not 0 <= r["quantity_reserved"] <= r["quantity_on_hand"]
            ],
        )
        self.check(
            "Reserved stock agrees with open unpicked orders",
            [
                r["id"]
                for r in b["inventory_levels"]
                if reserved[(r["warehouse_id"], r["sku"])] != r["quantity_reserved"]
            ],
        )
        self.check(
            "Sale ledger agrees with shipped order lines",
            [
                list(k)
                for k in set(sale) | set(expected_sale)
                if sale[k] != expected_sale[k]
            ],
        )
        balances = []
        holds = []
        for r in b["inventory_daily_balance"]:
            if not self.closed or r["balance_date"] > self.closed:
                continue
            end = r["balance_date"] + "T23:59:59"
            expected = sum(
                m["quantity_change"]
                for m in b["inventory_movements"]
                if m["warehouse_id"] == r["warehouse_id"]
                and m["sku"] == r["sku"]
                and m["movement_date"] <= end
            )
            if expected != r["quantity_on_hand"]:
                balances.append(r["id"])
            expected_hold = 0
            for o in b["orders"]:
                if o["created_at"] > end or (
                    o["cancelled_at"] and o["cancelled_at"] <= end
                ):
                    continue
                ship = self.ships.get(o["order_code"])
                if ship and ship["picked_at"] and ship["picked_at"] <= end:
                    continue
                meta = self.c["runtime"].get("order:" + str(o["id"]), {})
                if meta.get("warehouse") != r["warehouse_id"]:
                    continue
                expected_hold += sum(
                    x["quantity"]
                    for x in self.lines[o["id"]]
                    if self.idx["products"][x["product_id"]]["sku"] == r["sku"]
                )
            if expected_hold != r["quantity_reserved"]:
                holds.append(
                    {
                        "balance": r["id"],
                        "stored": r["quantity_reserved"],
                        "expected": expected_hold,
                    }
                )
        self.check(
            "Closed-day stock balances agree with historical movement ledger", balances
        )
        self.check(
            "Closed-day held stock reconstructed from order / pickup / cancellation times",
            holds,
        )
        self.findings["stock_totals"] = {
            k: sum(r[k] for r in b["inventory_levels"])
            for k in ["quantity_on_hand", "quantity_reserved"]
        }

    def analytics(self):
        b = self.b
        i = self.idx
        self.check(
            "Event inside session interval",
            [
                r["id"]
                for r in b["page_events"]
                if r["event_time"] < i["sessions"][r["session_id"]]["started_at"]
                or (
                    i["sessions"][r["session_id"]]["ended_at"]
                    and r["event_time"] > i["sessions"][r["session_id"]]["ended_at"]
                )
            ],
        )
        self.check(
            "Cart customer agrees with session",
            [
                r["id"]
                for r in b["cart_items"]
                if r["customer_id"] != i["sessions"][r["session_id"]]["customer_id"]
            ],
        )
        self.check(
            "Cart closure chronology",
            [
                r["id"]
                for r in b["cart_items"]
                if r["closed_at"] and r["closed_at"] < r["added_at"]
            ],
        )
        self.check(
            "Completed-day sessions closed",
            [
                r["id"]
                for r in b["sessions"]
                if self.closed
                and r["started_at"][:10] <= self.closed
                and not r["ended_at"]
                and self.c["runtime"].get(
                    "session_end:" + str(r["id"]), r["started_at"][:10] + "T23:59:59"
                )
                <= self.closed + "T23:59:59"
            ],
        )
        self.check(
            "Completed-day carts not left active",
            [
                r["id"]
                for r in b["cart_items"]
                if self.closed
                and r["added_at"][:10] <= self.closed
                and r["cart_status"] == "Active"
                and (
                    i["sessions"][r["session_id"]]["ended_at"] is not None
                    or self.c["runtime"].get(
                        "session_end:" + str(r["session_id"]),
                        r["added_at"][:10] + "T23:59:59",
                    )
                    <= self.closed + "T23:59:59"
                )
            ],
        )
        wrong = []
        for key, manifest in self.c["manifests"].items():
            action = self.c["action_results"].get(key, {})
            if self.c["jobs"].get(action.get("job"), {}).get("archived"):
                continue
            code = action.get("code", "")
            if not code.startswith(("GST-WEB-", "CUS-WEB-")):
                continue
            for x in manifest.get("changes", []):
                if x["table"] == "page_events" and x.get("after"):
                    event = x["after"]
                    if i["page_events"].get(event["id"]) != event:
                        continue
                    session = i["sessions"].get(event["session_id"])
                    if session and (
                        (code.startswith("GST") and session["customer_id"] is not None)
                        or (code.startswith("CUS") and session["customer_id"] is None)
                    ):
                        wrong.append(
                            {
                                "event_id": event["id"],
                                "code": code,
                                "at": action.get("at"),
                                "customer_id": session["customer_id"],
                            }
                        )
        self.check("Analytics actor agrees with guest/registered session", wrong)
        self.findings["actor_mismatch_by_code"] = dict(
            Counter(r["code"] for r in wrong)
        )
        self.findings["event_types"] = dict(
            Counter(r["event_type"] for r in b["page_events"])
        )
        self.findings["order_session_links"] = sum(
            r["session_id"] is not None for r in b["orders"]
        )
        self.findings["order_campaign_links"] = sum(
            r["campaign_id"] is not None for r in b["orders"]
        )
        self.findings["session_campaign_links"] = sum(
            r["campaign_id"] is not None for r in b["sessions"]
        )

    def marketing_finance(self):
        b = self.b
        self.check(
            "Ad reports inside campaign dates and budget",
            [
                r["id"]
                for r in b["marketing_campaigns"]
                if sum(
                    money(a["cost_amount"])
                    for a in b["ad_spend_logs"]
                    if a["campaign_id"] == r["id"]
                )
                > money(r["budget_amount"])
                or any(
                    not r["start_date"] <= a["log_date"] <= r["end_date"]
                    for a in b["ad_spend_logs"]
                    if a["campaign_id"] == r["id"]
                )
            ],
        )
        self.check(
            "Promotion dates and nonnegative limits",
            [
                r["id"]
                for r in b["promotions"]
                if r["end_date"] < r["start_date"]
                or money(r["discount_value"]) < 0
                or r["usage_limit"] < 0
            ],
        )
        overlap = []
        policies = b["seller_commission_rates"]
        for x, r in enumerate(policies):
            for other in policies[x + 1 :]:
                if (
                    (r["category_id"], r["seller_tier"])
                    == (other["category_id"], other["seller_tier"])
                    and r["effective_from"] <= (other["effective_to"] or "9999-12-31")
                    and other["effective_from"] <= (r["effective_to"] or "9999-12-31")
                ):
                    overlap.append([r["id"], other["id"]])
        self.check("Commission policy overlap", overlap)
        self.findings["money"] = {
            "completed_amount": float(
                sum(
                    money(r["final_amount"])
                    for r in b["orders"]
                    if r["order_status"] == "Completed"
                )
            ),
            "successful_payments": float(
                sum(
                    money(r["paid_amount"])
                    for r in b["payments"]
                    if r["payment_status"] == "Success"
                )
            ),
            "ad_spend": float(sum(money(r["cost_amount"]) for r in b["ad_spend_logs"])),
        }
        self.findings["commission_coverage_current_catalog"] = {
            "product_category_ids": sorted({r["category_id"] for r in b["products"]}),
            "policy_category_ids": sorted({r["category_id"] for r in policies}),
        }

    def control_checks(self):
        c = self.c
        days = []
        if self.closed:
            day = date.fromisoformat(c["settings"]["main"]["start_date"])
            while day.isoformat() <= self.closed:
                days.append(day.isoformat())
                day += timedelta(days=1)
        self.check(
            "Checkpoint daily records contiguous through closed cutoff",
            [d for d in days if d not in c["daily"]],
        )
        self.check(
            "No unavailable action was executed",
            [
                {"key": k, "code": r["code"]}
                for k, r in c["action_results"].items()
                if r.get("status") == "DONE"
                and not ACTIONS.get(r["code"], {}).get("available")
            ],
        )
        self.check(
            "Action ID deterministic / receipt ownership",
            [
                k
                for k, r in c["action_results"].items()
                if r.get("id")
                != hashlib.sha256(
                    f"{c['settings']['main']['seed']}:{r['at'][:10]}:{r['code']}:{r['order']}".encode()
                ).hexdigest()[:32]
                or k != r["job"] + ":" + r["id"]
            ],
        )
        grouped = defaultdict(list)
        for key, r in c["action_results"].items():
            grouped[(r["job"], r["at"][:10], r["code"])].append(r)
        wrong = []
        legacy = []
        expected_orders = Counter()
        actual_orders = Counter(o["created_at"][:10] for o in self.b["orders"])
        for day in days:
            daily = c["daily"].get(day, {})
            job = c["jobs"].get(daily.get("job"), {})
            plan = c["plans"].get(job.get("payload", {}).get("plan"), {})
            cfg = plan.get("config_snapshot")
            if cfg is None:
                legacy.append(job.get("payload", {}).get("plan"))
                cfg = c["versions"].get(plan.get("version"), {}).get("config", {})
            for code, entry in cfg.items():
                if not entry.get("enabled") or entry.get("mode") == "all":
                    continue
                expected = entry.get("special", {}).get(day, entry.get("count", 0))
                actions = grouped[(daily.get("job"), day, code)]
                if len(actions) != expected or sorted(
                    r["order"] for r in actions
                ) != list(range(expected)):
                    wrong.append(
                        {
                            "day": day,
                            "code": code,
                            "expected": expected,
                            "actual": len(actions),
                        }
                    )
                if code in ["GST-02", "CUS-05"]:
                    expected_orders[day] += expected
        self.check(
            "Completed-day action counts equal per-day replacement configuration", wrong
        )
        self.findings["legacy_plans_without_snapshot"] = sorted(
            {x for x in legacy if x}
        )
        self.findings["daily_order_counts"] = [
            {"day": d, "requested": expected_orders[d], "created": actual_orders[d]}
            for d in days
        ]
        self.findings["results_status"] = dict(
            Counter(r["status"] for r in c["action_results"].values())
        )
        self.findings["receipt_status"] = dict(
            Counter(r["status"] for r in c["receipts"].values())
        )
        self.findings["version_revisions"] = [
            {"id": k, "name": v["name"], "revision": v.get("revision", 1)}
            for k, v in c["versions"].items()
        ]
        self.findings["reset_history_count"] = len(c["resets"])

    def journal(self):
        c = self.c
        sync_errors = []
        images = defaultdict(list)
        row_actions = defaultdict(set)
        syncids = {k for k, v in c["jobs"].items() if v["kind"] == "sync"}
        for key, m in c["manifests"].items():
            jid = key.split(":")[0]
            for x in m.get("changes", []):
                if jid in syncids and (
                    x["table"] not in ["products", "sellers", "categories"]
                    or x["before"] is not None
                    or x["after"] is None
                ):
                    sync_errors.append({"key": key, "table": x["table"], "id": x["id"]})
                for image in [x["before"], x["after"]]:
                    if image is not None:
                        images[(x["table"], x["id"])].append(image)
                row_actions[(x["table"], x["id"])].add(
                    c["action_results"]
                    .get(key, {})
                    .get("code", c["jobs"].get(jid, {}).get("kind"))
                )
        self.check("All historical sync changes were catalog inserts only", sync_errors)
        unknown = []
        for n, rows in self.b.items():
            for r in rows:
                if not any(r == x for x in images[(n, r["id"])]):
                    unknown.append({"table": n, "id": r["id"]})
        self.check("Business snapshot row matches an available journal image", unknown)
        self.findings["manifest_status"] = dict(
            Counter(r["status"] for r in c["manifests"].values())
        )
        self.findings["mutation_action_codes"] = sorted(
            {code for codes in row_actions.values() for code in codes if code}
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = ReadOnlyAudit().run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "started_at",
                    "finished_at",
                    "counts",
                    "last_day_in_control",
                    "checked_closed_through",
                ]
            },
            ensure_ascii=False,
        )
    )
    print(
        json.dumps(
            [r for r in result["checks"] if r["violations"]],
            ensure_ascii=False,
            indent=2,
        )
    )
    print("Checks:", len(result["checks"]), "Output:", str(args.output))


if __name__ == "__main__":
    main()
