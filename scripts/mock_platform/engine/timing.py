"""Causal clocks: every transition follows its source, regardless of worker stages."""

from datetime import datetime, timedelta

from ..config.configuration import Distribution


class ActionClock:
    def __init__(self, engine):
        self.e = engine

    def source(self, table, row):
        e = self.e
        fields = {
            "customers": ("registration_date", "updated_at"),
            "sessions": ("started_at",),
            "cart_items": ("added_at",),
            "orders": ("created_at", "updated_at", "completed_at"),
            "payments": ("transaction_time",),
            "shipments": ("created_at", "picked_at", "in_transit_at", "failed_at"),
            "returns": ("requested_at", "approved_at", "received_at"),
            "refunds": ("requested_at",),
            "seller_payouts": ("paid_at",),
        }
        times = [row[k] for k in fields.get(table, ()) if row.get(k)]
        order = None
        if table in ("payments", "order_items", "refunds"):
            order = e.u.one("orders", row["order_id"])
        elif table == "shipments":
            order = e.u.lookup("orders", "order_code", row["order_code"])
        elif table == "returns":
            line = e.u.one("order_items", row["order_item_id"])
            order = e.u.one("orders", line["order_id"])
        elif table == "orders":
            order = row
        if order:
            times.extend(order[k] for k in ("created_at", "updated_at") if order.get(k))
            if e.code == "ORD-01":
                if not hasattr(e, "_payment_times"):
                    p = e.db.bm.tables["payments"]
                    from sqlalchemy import func, select

                    e._payment_times = dict(
                        e.u.conn.execute(
                            select(p.c.order_id, func.max(p.c.transaction_time))
                            .where(p.c.payment_status == "Success")
                            .group_by(p.c.order_id)
                        ).all()
                    )
                paid = e._payment_times.get(order["id"])
                if paid:
                    times.append(
                        paid.isoformat() if isinstance(paid, datetime) else paid
                    )
        if table in ("sessions", "cart_items"):
            session = (
                row if table == "sessions" else e.u.one("sessions", row["session_id"])
            )
            if session.get("customer_id"):
                customer = e.u.one("customers", session["customer_id"])
                times.append(customer["registration_date"])
        transition = (
            e.getmeta(f"last_transition:{table}:{row['id']}")
            if table == "seller_payouts"
            else None
        )
        if transition:
            times.append(transition)
        return max(times) if times else None

    def at(self, table, row):
        e = self.e
        source = self.source(table, row)
        if e.a.get("timing", {}).get("offset_seconds") and table in (
            "sessions",
            "cart_items",
        ):
            session = (
                row if table == "sessions" else e.u.one("sessions", row["session_id"])
            )
            return e.session_time(session)
        if not source:
            return e.now
        seconds = e.a.get("timing", {}).get("after_seconds")
        delta = (
            Distribution.sample(seconds, e.a.get("seed", 42), e.a["id"] + ":after")
            if seconds
            else 0
        )
        delta += int(e.p.get("_delay_days", 0)) * 86400
        return max(
            e.now,
            (datetime.fromisoformat(source) + timedelta(seconds=delta)).isoformat(
                timespec="seconds"
            ),
        )

    def allowed(self, at):
        e = self.e
        if at[:10] != e.day:
            return False
        availability = getattr(e.binding, "pool", {}).get("availability", {})
        if availability and not availability["start"] <= at[11:] <= availability["end"]:
            return False
        spec = e.a.get("timing", {})
        return (not spec.get("start") or at[11:] >= spec["start"]) and (
            not spec.get("end") or at[11:] <= spec["end"]
        )
