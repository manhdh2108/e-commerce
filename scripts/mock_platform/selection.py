"""Apply cheap SQL scope filters before Python business predicates."""

from sqlalchemy import select

from .storage import clean


class EligibleTargetSelector:
    def __init__(self, engine):
        self.e = engine

    def rows(self, name, target):
        e = self.e
        table = e.db.bm.tables[name]
        query = select(table)
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
        return [
            clean(dict(r))
            for r in e.u.conn.execute(query.order_by(table.c.id)).mappings()
        ]
