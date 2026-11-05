import hashlib
import time
import traceback
from .storage import UnitOfWork
from .domain import DomainEngine, NotEligible
from .service import PlatformService, ACTIONS, stamp


class Worker:
    def __init__(self, service=None):
        self.s = service or PlatformService()
        self.db = self.s.db

    def apply_effects(self, effects, c):
        for effect in effects:
            self.db.put("runtime", effect["key"], effect["value"], c)

    def finish(self, key, manifest):
        with self.db.control.begin() as c:
            self.apply_effects(manifest.get("effects", []), c)
            self.db.put(
                "receipts",
                key,
                {
                    "status": "DONE",
                    "message": manifest.get("message", ""),
                    "at": stamp(),
                    "changes": len(manifest["changes"]),
                },
                c,
            )
            self.db.put("manifests", key, {**manifest, "status": "DONE"}, c)
            self.db.put(
                "revision", "main", self.db.get("revision", "main", 0, c) + 1, c
            )

    def recover(self, key, manifest):
        # Fold repeated modifications of a row into first/last images.
        grouped = {}
        for item in manifest["changes"]:
            k = (item["table"], item["id"])
            if k not in grouped:
                grouped[k] = dict(item)
            else:
                grouped[k]["after"] = item["after"]
        with self.db.business.connect() as c:
            u = UnitOfWork(self.db, c)
            images = [(u.one(x["table"], x["id"]), x) for x in grouped.values()]
        if all(row == x["after"] for row, x in images):
            self.finish(key, manifest)
            return True
        if all(row == x["before"] for row, x in images):
            return False
        raise RuntimeError(
            "Không đủ bằng chứng phục hồi batch. DB đích khác manifest; cần kiểm tra, không retry mù."
        )

    def transact(self, key, callback):
        receipt = self.db.get("receipts", key)
        if receipt:
            return receipt
        prepared = self.db.get("manifests", key)
        if prepared and self.recover(key, prepared):
            return self.db.get("receipts", key)
        with self.db.business.connect() as conn:
            tx = conn.begin()
            u = UnitOfWork(self.db, conn)
            try:
                result = callback(u) or {}
                manifest = {
                    "status": "PREPARED",
                    "changes": u.changes,
                    "effects": result.get("effects", []),
                    "message": result.get("message", ""),
                }
                self.db.put("manifests", key, manifest)
                tx.commit()
            except BaseException:
                tx.rollback()
                raise
        self.finish(key, manifest)
        return self.db.get("receipts", key)

    def sync(self, jid, job):
        preview = self.db.get("sync_previews", job["payload"]["preview"])
        at = self.s.summary()["next_day"] + "T00:00:00"
        for i, prod in enumerate(preview["products"]):
            if self.paused(jid):
                return False

            def add(u):
                if u.one("products", prod["id"]):
                    return {"message": "Bỏ qua: đã có."}
                root, leaf = prod["root_id"], prod["leaf_id"]
                for cid, parent in [
                    (root, None),
                    (leaf, root if leaf != root else None),
                ]:
                    if not u.one("categories", cid):
                        u.add(
                            "categories",
                            id=cid,
                            category_name=(
                                prod.get("category_name")
                                if cid == root
                                else prod.get("raw", {})
                                .get("visible_impression_info", {})
                                .get("amplitude", {})
                                .get("primary_category_name")
                            )
                            or f"Danh mục Tiki {cid}",
                            parent_id=parent,
                            level=1 if parent is None else 2,
                            slug=f"tiki-{cid}",
                        )
                if not u.one("sellers", prod["seller_id"]):
                    u.add(
                        "sellers",
                        id=prod["seller_id"],
                        seller_name=f"Người bán mô phỏng {prod['seller_id']}",
                        shop_name=f"Shop {prod['seller_id']}",
                        tier="Normal",
                        province="TP. Hồ Chí Minh",
                        city="TP. Hồ Chí Minh",
                        email=f"seller{prod['seller_id']}@example.com",
                        status="Active",
                        created_at=at,
                        updated_at=at,
                    )
                values = {
                    k: prod.get(k)
                    for k in self.db.bm.tables["products"].c.keys()
                    if k not in ["leaf_id", "root_id", "raw"]
                }
                values.update(
                    category_id=leaf,
                    category_name=u.one("categories", leaf)["category_name"],
                    seller_product_id=str(prod["seller_product_id"])
                    if prod.get("seller_product_id") is not None
                    else None,
                    is_active=preview.get("new_active", True)
                    and u.one("sellers", prod["seller_id"])["status"] == "Active",
                    created_at=at,
                    updated_at=at,
                    cost_price=None,
                )
                for k in ["stock_item"]:
                    if isinstance(values[k], (dict, list)):
                        values[k] = __import__("json").dumps(
                            values[k], ensure_ascii=False
                        )
                u.add("products", **values)
                return {
                    "effects": [
                        {
                            "key": f"provenance:{prod['id']}",
                            "value": {
                                "source": "Tiki",
                                "snapshot": job["payload"]["preview"],
                                "imported_at": at,
                                "source_active": prod.get("is_active"),
                                "note": "Trạng thái bán là mô phỏng; danh mục trung gian chưa có dữ liệu xác minh.",
                            },
                        }
                    ]
                }

            self.transact(f"{jid}:sync:{prod['id']}", add)
            job.update(
                completed=i + 1,
                message=f"Đã xét {i + 1}/{len(preview['products'])} sản phẩm",
            )
            self.db.put("jobs", jid, job)
        return True

    def bootstrap(self, jid, job):
        p = job["payload"]
        at = self.s.setup()["start_date"] + "T00:00:00"

        def add(u):
            if self.db.get("bootstrap", "done"):
                raise ValueError("Dữ liệu nền đã tạo; không tự tạo lại.")
            for name in ["Web", "App", "Livestream"]:
                if not any(r["channel_name"] == name for r in u.rows("channels")):
                    u.add("channels", channel_name=name, channel_type="Digital")
            for name, group in [
                ("COD", "COD"),
                ("Momo", "E-Wallet"),
                ("ZaloPay", "E-Wallet"),
                ("Credit Card", "Card"),
                ("Bank Transfer", "Bank Transfer"),
            ]:
                if not any(r["method_name"] == name for r in u.rows("payment_methods")):
                    u.add("payment_methods", method_name=name, method_group=group)
            if not u.rows("warehouses"):
                u.add(
                    "warehouses",
                    warehouse_code="WH-DEMO",
                    warehouse_name="Kho mô phỏng",
                    province="TP. Hồ Chí Minh",
                    city="TP. Hồ Chí Minh",
                    address="Địa chỉ kho thử nghiệm",
                )
            if not u.rows("carriers"):
                u.add(
                    "carriers", carrier_code="DEMO", carrier_name="Vận chuyển mô phỏng"
                )
            for i in range(p.get("customers", 0)):
                u.add(
                    "customers",
                    full_name=f"Khách nền {i + 1}",
                    email=f"baseline.{jid}.{i}@example.com",
                    phone_number="0900000000",
                    province="TP. Hồ Chí Minh",
                    city="TP. Hồ Chí Minh",
                    membership_tier="Member",
                    registration_date=at,
                    updated_at=at,
                )
            stock = int(p.get("stock", 0))
            wh = u.rows("warehouses")[0]
            if stock:
                for prod in u.rows("products"):
                    if any(
                        r["sku"] == prod["sku"] and r["warehouse_id"] == wh["id"]
                        for r in u.rows("inventory_levels")
                    ):
                        continue
                    u.add(
                        "inventory_levels",
                        warehouse_id=wh["id"],
                        sku=prod["sku"],
                        quantity_on_hand=stock,
                        quantity_reserved=0,
                        updated_at=at,
                    )
                    u.add(
                        "inventory_movements",
                        warehouse_id=wh["id"],
                        sku=prod["sku"],
                        movement_type="Import",
                        quantity_change=stock,
                        reference_code="INITIAL",
                        movement_date=at,
                    )
            return {"effects": [{"key": "bootstrap_done", "value": True}]}

        self.transact(f"{jid}:bootstrap", add)
        self.db.put("bootstrap", "done", True)
        return True

    def paused(self, id):
        return self.db.get("commands", id, {}).get("pause", False)

    def run(self, jid, job):
        plan = self.s.execution_plan(job["payload"]["plan"])
        cfg = plan["config_snapshot"]
        seed = self.s.setup().get("seed", 42)
        priority = {
            "GST-01": 0,
            "WH-01": 1,
            "GST-WEB-01": 2,
            "CUS-WEB-01": 2,
            "GST-02": 3,
            "CUS-05": 3,
            "PAY-01": 4,
            "ORD-01": 5,
            "DSP-01": 6,
            "WH-03": 7,
            "CAR-01": 7,
            "CAR-02": 8,
            "CAR-03": 9,
            "CAR-04": 10,
            "CUS-09": 11,
            "AUT-WH-04": 15,
            "MKT-01": 0,
            "MKT-03": 0,
            "MKT-04": 0,
            "SHOP-MKT-01": 0,
            "FIN-POL-01": 0,
            "MKT-02": 1,
            "ADS-01": 13,
            "AUT-WEB-01": 14,
            "AUT-WEB-02": 15,
            **{f"{kind}-WEB-{i:02}": 2 for kind in ["GST", "CUS"] for i in range(1, 7)},
        }
        for day in plan["days"]:
            if self.paused(jid):
                return False
            saved = self.db.get("checkpoint", "main", {}).get("last_day")
            if saved and day["day"] <= saved:
                continue
            requested = 0
            for code, entry in sorted(
                cfg.items(), key=lambda item: (priority.get(item[0], 12), item[0])
            ):
                if not entry.get("enabled"):
                    continue
                automatic = entry.get("mode") == "all"
                count = entry.get("special", {}).get(day["day"], entry.get("count", 0))
                requested += count if not automatic else 0
                params = {f["key"]: f.get("default") for f in ACTIONS[code]["fields"]}
                params.update(entry.get("params", {}))
                index = 0
                while automatic or index < count:
                    if self.paused(jid):
                        return False
                    if index >= 100000:
                        raise RuntimeError(
                            "Vượt ngưỡng bảo vệ 100.000 lần cho một hành động/ngày. Cần kiểm tra phạm vi đầu vào."
                        )
                    aid = hashlib.sha256(
                        f"{seed}:{day['day']}:{code}:{index}".encode()
                    ).hexdigest()[:32]
                    at = day["day"] + f"T{8 + priority.get(code, 12):02}:00:00"
                    action = {
                        "id": aid,
                        "code": code,
                        "at": at,
                        "params": params,
                        "order": index,
                    }
                    index += 1
                    key = f"{jid}:{aid}"
                    receipt = self.db.get("receipts", key)
                    if receipt:
                        if not self.db.get("action_results", key):
                            self.db.put(
                                "action_results", key, {"job": jid, **action, **receipt}
                            )
                        if automatic and receipt["status"] == "EXHAUSTED":
                            break
                        continue
                    job.update(
                        day=day["day"],
                        heartbeat=stamp(),
                        message=f"{code} · {ACTIONS[code]['label']}",
                    )
                    self.db.put("jobs", jid, job)

                    def apply(u):
                        with self.db.control.connect() as c:
                            state = {
                                r.id: r.data
                                for r in c.execute(
                                    __import__("sqlalchemy")
                                    .select(self.db.records)
                                    .where(self.db.records.c.kind == "runtime")
                                )
                            }
                        engine = DomainEngine(self.db, u, action, state)
                        engine.execute()
                        return {"effects": engine.effects, "message": code}

                    try:
                        result = self.transact(key, apply)
                        self.db.put(
                            "action_results",
                            key,
                            {
                                "job": jid,
                                **action,
                                "status": "DONE",
                                "changes": result["changes"],
                            },
                        )
                        job["completed"] = job.get("completed", 0) + 1
                    except NotEligible as exc:
                        status = "EXHAUSTED" if automatic else "REJECTED"
                        self.db.put(
                            "receipts", key, {"status": status, "message": str(exc)}
                        )
                        self.db.put(
                            "action_results",
                            key,
                            {
                                "job": jid,
                                **action,
                                "status": status,
                                "message": str(exc),
                            },
                        )
                        if automatic:
                            break
                        job["rejected"] = job.get("rejected", 0) + 1
                    self.db.put("jobs", jid, job)
                    pause = float(job["payload"].get("delay_ms", 0)) / 1000
                    if pause:
                        time.sleep(min(pause, 1))
            from .validation import BusinessValidator

            report = BusinessValidator(self.db).report()
            if not report["ok"]:
                self.db.put("validation", jid, {"day": day["day"], **report})
                raise RuntimeError(
                    "Kiểm tra dữ liệu cuối ngày không đạt, chưa mở ngày tiếp theo."
                )
            with self.db.control.begin() as connection:
                self.db.put(
                    "checkpoint",
                    "main",
                    {"last_day": day["day"], "job": jid},
                    connection,
                )
                self.db.put(
                    "daily",
                    day["day"],
                    {"job": jid, "requested": requested},
                    connection,
                )
        return True

    def tick(self):
        jobs = sorted(
            [j for j in self.db.list("jobs") if j["status"] in ["QUEUED", "RUNNING"]],
            key=lambda j: j["created_at"],
        )
        if not jobs:
            return False
        job = jobs[0]
        jid = job.pop("id")
        with self.db.writer():
            job["status"] = "RUNNING"
            job["heartbeat"] = stamp()
            self.db.put("jobs", jid, job)
            try:
                kind = job["kind"]
                complete = (
                    self.sync(jid, job)
                    if kind == "sync"
                    else self.bootstrap(jid, job)
                    if kind == "bootstrap"
                    else self.run(jid, job)
                )
                job["status"] = "COMPLETE" if complete else "PAUSED"
                job["message"] = "Hoàn tất" if complete else "Đã tạm dừng an toàn"
            except Exception as exc:
                traceback.print_exc()
                job["status"] = "FAILED"
                job["message"] = (
                    str(exc)
                    if isinstance(exc, (ValueError, RuntimeError))
                    else "Lỗi kỹ thuật khi ghi dữ liệu. Xem log worker; không tự chạy lại batch chưa đối chiếu."
                )
            results = [r for r in self.db.list("action_results") if r.get("job") == jid]
            job["completed"] = (
                sum(r["status"] == "DONE" for r in results)
                if results
                else job.get("completed", 0)
            )
            job["rejected"] = sum(r["status"] == "REJECTED" for r in results)
            job["finished_at"] = stamp()
            self.db.put("jobs", jid, job)
        return True

    def loop(self):
        self.db.start_control()
        while True:
            try:
                if not self.tick():
                    time.sleep(1)
            except KeyboardInterrupt:
                break
            except Exception:
                traceback.print_exc()
                time.sleep(2)
