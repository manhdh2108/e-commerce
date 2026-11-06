"""Apply cheap SQL scope filters before Python business predicates."""

from sqlalchemy import exists, select

from ..infrastructure.storage import clean


class EligibleTargetSelector:
    def __init__(self, engine):
        self.e = engine

    def rows(self, name, target):
        e = self.e
        table = e.db.bm.tables[name]
        query = select(table)
        from ..config.configuration import resolve_filters, sql_filter, validate_filters

        filters = {**e.a.get("selection", {}).get(name, {}), **e.binding.filters(name)}
        filters = resolve_filters(filters, e)
        validate_filters(filters, table.c.keys())
        for field, values in filters.items():
            query = query.where(sql_filter(table.c[field], values))
        if (
            name == "sessions"
            and not e.code.startswith("AUT-WEB")
            and not e.a.get("timing", {}).get("offset_seconds")
        ):
            query = query.where(table.c.started_at <= e.now)
        if target:
            try:
                identity = int(target)
            except (ValueError, TypeError):
                return []
            query = query.where(table.c.id == identity)
        if name == "sessions":
            query = query.where(table.c.ended_at.is_(None))
            if e.code.startswith("GST-WEB"):
                query = query.where(table.c.customer_id.is_(None))
            elif e.code.startswith("CUS-WEB"):
                query = query.where(table.c.customer_id.is_not(None))
        if name == "cart_items":
            query = query.where(table.c.cart_status == "Active")
            sessions = e.db.bm.tables["sessions"]
            query = query.join(sessions, table.c.session_id == sessions.c.id)
            query = query.where(
                sessions.c.ended_at.is_not(None)
                if e.code == "AUT-WEB-02"
                else sessions.c.ended_at.is_(None)
            )
            if e.code.startswith("GST-WEB"):
                query = query.where(sessions.c.customer_id.is_(None))
            elif e.code.startswith("CUS-WEB"):
                query = query.where(sessions.c.customer_id.is_not(None))
        if (
            name == "products"
            and e.code in ("CUS-05", "GST-02")
            and e.p.get("checkout_mode", "direct") == "direct"
        ):
            inv = e.db.bm.tables["inventory_levels"]
            stock = select(inv.c.id).where(
                inv.c.sku == table.c.sku,
                inv.c.quantity_on_hand - inv.c.quantity_reserved
                >= int(e.p.get("quantity", 1)),
            )
            if e.p.get("warehouse"):
                stock = stock.where(inv.c.warehouse_id == e.p["warehouse"])
            query = query.where(table.c.is_active.is_(True), exists(stock))
        statuses = {
            ("PAY-01", "payments"): ("payment_status", ["Pending"]),
            ("ORD-01", "orders"): ("order_status", ["Pending"]),
            ("DSP-01", "orders"): ("order_status", ["Processing"]),
            ("CAR-04", "orders"): ("order_status", ["Completed"]),
            ("CAR-01", "shipments"): ("shipment_status", ["Created"]),
            ("WH-03", "shipments"): ("shipment_status", ["Created"]),
            ("CAR-02", "shipments"): ("shipment_status", ["Picked"]),
            ("CAR-03", "shipments"): ("shipment_status", ["In Transit"]),
            ("CAR-05", "shipments"): ("shipment_status", ["Failed"]),
            ("CAR-06", "shipments"): ("shipment_status", ["Failed"]),
            ("SUP-01", "returns"): ("status", ["Requested"]),
            ("SUP-02", "returns"): ("status", ["Requested"]),
            ("WH-04", "returns"): ("status", ["Approved"]),
            ("PAY-02", "refunds"): ("refund_status", ["Pending"]),
        }
        status = statuses.get((e.code, name))
        if status:
            query = query.where(table.c[status[0]].in_(status[1]))
        rows = [
            clean(dict(r))
            for r in e.u.conn.execute(query.order_by(table.c.id)).mappings()
        ]

        self.prepare(name, rows)
        return rows

    def prepare(self, name, rows):
        e = self.e
        keys = []
        if name == "seller_payouts":
            keys.extend(f"last_transition:{name}:{row['id']}" for row in rows)
        if e.code in ("PAY-02", "FIN-PAY-01") and name in ("refunds", "seller_payouts"):
            keys.extend(f"next_attempt:{name}:{row['id']}:{e.code}" for row in rows)
        orders = []
        if name == "sessions":
            keys.extend(
                prefix + str(r["id"])
                for r in rows
                for prefix in ("session_end:", "session_last:", "session_actor:")
            )
            e.u.prefetch_by(
                "customers",
                "id",
                [r["customer_id"] for r in rows if r["customer_id"] is not None],
            )
        if name == "cart_items":
            e.u.prefetch_by("sessions", "id", [r["session_id"] for r in rows])
            sessions = [e.u.one("sessions", r["session_id"]) for r in rows]
            self.prepare("sessions", [r for r in sessions if r])
        if name == "orders":
            orders = rows
            if e.binding.pending and e.binding.pending["entity"] == "carriers":
                e.u.prefetch_by(
                    "shipments", "order_code", [r["order_code"] for r in rows]
                )
        elif name in ("payments", "order_items", "refunds"):
            e.u.prefetch_by("orders", "id", [r["order_id"] for r in rows])
            orders = [e.u.one("orders", r["order_id"]) for r in rows]
        elif name == "returns":
            e.u.prefetch_by("order_items", "id", [r["order_item_id"] for r in rows])
            lines = [e.u.one("order_items", r["order_item_id"]) for r in rows]
            e.u.prefetch_by("orders", "id", [r["order_id"] for r in lines])
            orders = [e.u.one("orders", r["order_id"]) for r in lines]
        elif name == "shipments":
            e.u.prefetch_by("orders", "order_code", [r["order_code"] for r in rows])
            orders = [e.u.lookup("orders", "order_code", r["order_code"]) for r in rows]
        orders = [r for r in orders if r]
        keys.extend("order:" + str(r["id"]) for r in orders)
        pending = e.binding.pending
        if pending:
            entity = pending["entity"]
            if entity in ("customers", "sellers") and orders:
                field = "customer_id" if entity == "customers" else "seller_id"
                e.u.prefetch_by(entity, "id", [r[field] for r in orders])
            if entity == "carriers" and name == "shipments":
                e.u.prefetch_by(entity, "id", [r["carrier_id"] for r in rows])
        if hasattr(e.state, "prefetch"):
            e.state.prefetch(keys)
