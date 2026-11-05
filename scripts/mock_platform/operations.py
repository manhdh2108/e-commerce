"""Read-only OLTP dashboard and explicit, journalled environment reset."""

from sqlalchemy import select, func, delete, cast, String, inspect
from .service import stamp, uid, ConfigurationConflict
from .storage import clean


class DataOperations:
    def __init__(self, service):
        self.s, self.db = service, service.db

    def dashboard(self):
        if not self.s.summary()["ready"]:
            return {"ready": False}
        tables = self.db.bm.tables
        with self.db.business.connect() as c:

            def total(table, field, condition=None):
                q = select(func.coalesce(func.sum(tables[table].c[field]), 0))
                if condition is not None:
                    q = q.where(condition)
                return c.execute(q).scalar()

            def groups(table, field):
                t = tables[table]
                return [
                    {"status": r[0] or "Chưa xác định", "count": r[1]}
                    for r in c.execute(
                        select(t.c[field], func.count()).group_by(t.c[field])
                    )
                ]

            orders = tables["orders"]
            day = func.substr(cast(orders.c.created_at, String), 1, 10)
            daily = [
                dict(r)
                for r in c.execute(
                    select(
                        day.label("day"),
                        func.count().label("orders"),
                        func.sum(orders.c.final_amount).label("amount"),
                    )
                    .group_by(day)
                    .order_by(day.desc())
                    .limit(30)
                ).mappings()
            ]
            onhand = total("inventory_levels", "quantity_on_hand")
            reserved = total("inventory_levels", "quantity_reserved")
            return clean(
                {
                    "ready": True,
                    "checked_at": stamp(),
                    "order_amount": total("orders", "final_amount"),
                    "completed_amount": total(
                        "orders", "final_amount", orders.c.order_status == "Completed"
                    ),
                    "paid_amount": total(
                        "payments",
                        "paid_amount",
                        tables["payments"].c.payment_status == "Success",
                    ),
                    "ad_cost": total("ad_spend_logs", "cost_amount"),
                    "on_hand": onhand,
                    "reserved": reserved,
                    "available": onhand - reserved,
                    "orders": groups("orders", "order_status"),
                    "payments": groups("payments", "payment_status"),
                    "shipments": groups("shipments", "shipment_status"),
                    "daily_orders": list(reversed(daily)),
                }
            )

    def backlog(self):
        if not self.s.summary()["ready"]:
            return []
        stages = [
            ("payments", "payment_status", "Pending", "Chờ kết quả thanh toán"),
            ("orders", "order_status", "Pending", "Đơn chờ thanh toán / xác nhận"),
            ("orders", "order_status", "Processing", "Đơn đã xác nhận"),
            ("shipments", "shipment_status", "In Transit", "Đang giao"),
            ("shipments", "shipment_status", "Failed", "Giao thất bại chờ xử lý"),
            ("returns", "status", "Requested", "Chờ xét yêu cầu trả"),
            ("returns", "status", "Approved", "Chờ nhận hàng trả"),
            ("refunds", "refund_status", "Pending", "Chờ hoàn tiền"),
        ]
        with self.db.business.connect() as c:
            return [
                {
                    "label": label,
                    "count": c.execute(
                        select(func.count())
                        .select_from(self.db.bm.tables[table])
                        .where(self.db.bm.tables[table].c[field] == status)
                    ).scalar(),
                }
                for table, field, status, label in stages
            ]

    def sync_status(self):
        jobs = sorted(
            [j for j in self.db.list("jobs") if j["kind"] == "sync"],
            key=lambda j: j.get("finished_at", j["created_at"]),
            reverse=True,
        )
        last = next(
            (j for j in jobs if j["status"] == "COMPLETE" and not j.get("archived")),
            None,
        )
        return {"last_sync": last, "last_attempt": jobs[0] if jobs else None}

    def check_source(self):
        preview = self.s.source_preview({"limit": 0}, persist=False)
        return {**preview, "checked_at": stamp(), **self.sync_status()}

    def reset_preview(self):
        # Serialize the counts/revision with workers. No business changes.
        with self.db.writer():
            if set(inspect(self.db.business).get_table_names()) != set(
                self.db.bm.tables
            ):
                raise ValueError(
                    "Cấu trúc OLTP không đủ hoặc có bảng ngoài mô hình; cần kiểm tra trước khi xóa."
                )
            info = self.s.summary()
            if not info["ready"]:
                raise ValueError("Chưa chuẩn bị môi trường.")
            preview = {
                "counts": info["counts"],
                "total": sum(info["counts"].values()),
                "revision": self.db.get("revision", "main", 0),
                "last_day": info["last_day"],
                "created_at": stamp(),
            }
            key = uid()
            self.db.put("reset_previews", key, preview)
            return {"id": key, **preview}

    def validate_reset(self, payload):
        if payload.get("confirmation") != "XOA TOAN BO":
            raise ValueError("Nhập chính xác XOA TOAN BO để xác nhận.")
        preview = self.db.get("reset_previews", payload.get("preview"))
        if not preview or preview["revision"] != self.db.get("revision", "main", 0):
            raise ConfigurationConflict(
                "Dữ liệu đã thay đổi. Hãy xem trước việc xóa lại."
            )
        info = self.s.summary()
        if (
            preview["counts"] != info["counts"]
            or preview["last_day"] != info["last_day"]
        ):
            raise ConfigurationConflict(
                "Số dòng đã thay đổi. Hãy xem trước việc xóa lại."
            )

    def reset(self, worker, jid, job):
        def remove(u):
            for t in reversed(self.db.bm.sorted_tables):
                rows = u.rows(t.name)
                u.changes.extend(
                    {"table": t.name, "id": r["id"], "before": r, "after": None}
                    for r in rows
                )
                u.conn.execute(delete(t))
            return {"message": "Đã xóa toàn bộ dữ liệu OLTP.", "reset": True}

        worker.transact(f"{jid}:reset", remove)
        job["completed"] = self.db.get("receipts", f"{jid}:reset")["changes"]
        return True

    def finish_reset(self, connection, jid):
        """Called in the same Control transaction as the reset receipt/revision."""
        connection.execute(
            delete(self.db.records).where(
                self.db.records.c.kind.in_(
                    ["runtime", "checkpoint", "bootstrap", "daily"]
                )
            )
        )
        rows = connection.execute(
            select(self.db.records).where(self.db.records.c.kind == "jobs")
        ).all()
        for r in rows:
            if r.id == jid:
                continue
            job = {**r.data, "archived": True}
            if job["status"] != "COMPLETE":
                job.update(status="CANCELLED", message="Đã hủy do xóa toàn bộ OLTP.")
            self.db.put("jobs", r.id, job, connection)
        self.db.put("lifecycle", "reset", True, connection)
        self.db.put("resets", jid, {"finished_at": stamp()}, connection)
