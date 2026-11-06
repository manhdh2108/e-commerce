import hashlib
import time
import traceback

from ..engine.domain import DomainEngine, NotEligible
from ..infrastructure.storage import UnitOfWork
from .service import ACTIONS, PlatformService, stamp


class Worker:
    def __init__(self, service=None):
        self.s = service or PlatformService()
        self.db = self.s.db

    def apply_effects(self, effects, c):
        for effect in effects:
            self.db.put("runtime", effect["key"], effect["value"], c)

    def finish(self, key, manifest):
        with self.db.control.begin() as c:
            if self.db.get("receipts", key, None, c):
                return
            for effect in manifest.get("effects", []):
                current = self.db.get("runtime", effect["key"], None, c)
                before = manifest.get("effect_before", {}).get(effect["key"])
                if (
                    "effect_before" in manifest
                    and current != before
                    and current != effect["value"]
                ):
                    raise RuntimeError(
                        "Runtime khác ảnh trước/sau của journal; không phục hồi mù."
                    )
            sequence = self.db.get("commit_sequence", "main", 0, c) + 1
            self.db.put("commit_sequence", "main", sequence, c)
            if manifest.get("reset"):
                from .operations import DataOperations

                DataOperations(self.s).finish_reset(c, key.split(":")[0])
            self.apply_effects(manifest.get("effects", []), c)
            self.db.put(
                "receipts",
                key,
                {
                    "status": "DONE",
                    "commit_sequence": sequence,
                    "resolved_params": manifest.get("resolved_params"),
                    "selected_ids": manifest.get("selected_ids", {}),
                    "effective_at": manifest.get("effective_at"),
                    "actor": manifest.get("actor"),
                    "message": manifest.get("message", ""),
                    "at": stamp(),
                    "changes": len(manifest["changes"]),
                },
                c,
            )
            self.db.put(
                "manifests",
                key,
                {**manifest, "status": "DONE", "commit_sequence": sequence},
                c,
            )
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
                    "reset": result.get("reset", False),
                    "changes": u.changes,
                    "effects": result.get("effects", []),
                    "effect_before": {
                        effect["key"]: self.db.get("runtime", effect["key"])
                        for effect in result.get("effects", [])
                    },
                    "resolved_params": result.get("resolved_params"),
                    "selected_ids": result.get("selected_ids", {}),
                    "effective_at": result.get("effective_at"),
                    "actor": result.get("actor"),
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
                    from ..engine.entities import EntityGenerator

                    generator = EntityGenerator(
                        job["payload"].get("entity_profile") or self.s.entity_profile(),
                        job["payload"].get("seed", self.s.setup().get("seed", 42)),
                    )
                    seller_attributes = generator.seller(
                        "seller:" + str(prod["seller_id"])
                    )
                    u.add(
                        "sellers",
                        id=prod["seller_id"],
                        seller_name=seller_attributes.get(
                            "seller_name", f"Cửa hàng {prod['seller_id']}"
                        ),
                        phone=seller_attributes.get("phone"),
                        shop_name=seller_attributes.get(
                            "shop_name", f"Shop {prod['seller_id']}"
                        ),
                        tier=seller_attributes.get("tier", "Normal"),
                        province=seller_attributes.get("province", "TP. Hồ Chí Minh"),
                        city=seller_attributes.get("city", "TP. Hồ Chí Minh"),
                        email=seller_attributes.get(
                            "email", f"contact.{prod['seller_id']}@example.com"
                        ),
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
            profile = p.get("entity_profile") or {}
            from ..config.configuration import DEFAULTS

            for channel in profile.get("channels", DEFAULTS["channels"]):
                if not any(
                    r["channel_name"] == channel["channel_name"]
                    for r in u.rows("channels")
                ):
                    u.add("channels", **channel)
            for method in profile.get("payment_methods", DEFAULTS["payment_methods"]):
                if not any(
                    r["method_name"] == method["method_name"]
                    for r in u.rows("payment_methods")
                ):
                    u.add("payment_methods", **method)
            from ..engine.entities import EntityGenerator

            generator = EntityGenerator(p.get("entity_profile"), p.get("seed", 42))
            for table in ["warehouses", "carriers"]:
                code = "warehouse_code" if table == "warehouses" else "carrier_code"
                for row in generator.p[table]:
                    if not any(r[code] == row[code] for r in u.rows(table)):
                        u.add(table, **row)
            for i in range(p.get("customers", 0)):
                registered_at = at
                history = generator.p.get("bootstrap", {}).get("customer_history_days")
                if history:
                    from datetime import datetime, timedelta

                    from ..config.configuration import Distribution, rng

                    age = Distribution.sample(
                        history, generator.seed, f"baseline-age:{i}"
                    )
                    seconds = rng(generator.seed, f"baseline-time:{i}").randrange(86400)
                    registered_at = (
                        datetime.fromisoformat(at)
                        - timedelta(days=age, seconds=seconds)
                    ).isoformat(timespec="seconds")
                u.add("customers", **generator.person(f"baseline:{i}", registered_at))
            stock = int(p.get("stock", 0))
            rules = generator.p.get("inventory")
            if stock or rules:
                from ..config.configuration import Distribution, matches, rng

                existing = {
                    (r["sku"], r["warehouse_id"]) for r in u.rows("inventory_levels")
                }
                products = list(u.rows("products"))
                for wh in u.rows("warehouses"):
                    for prod in products:
                        if (prod["sku"], wh["id"]) in existing:
                            continue
                        quantity = stock
                        if rules is not None:
                            rule = next(
                                (
                                    r
                                    for r in rules
                                    if matches(prod, r.get("products", {}))
                                    and matches(wh, r.get("warehouses", {}))
                                ),
                                None,
                            )
                            if rule is None:
                                continue
                            identity = f"stock:{prod['id']}:{wh['warehouse_code']}"
                            if rng(
                                generator.seed, identity + ":coverage"
                            ).random() >= rule.get("coverage", 1):
                                continue
                            quantity = Distribution.sample(
                                rule["quantity"], generator.seed, identity
                            )
                        if not quantity:
                            continue
                        u.add(
                            "inventory_levels",
                            warehouse_id=wh["id"],
                            sku=prod["sku"],
                            quantity_on_hand=quantity,
                            quantity_reserved=0,
                            updated_at=at,
                        )
                        u.add(
                            "inventory_movements",
                            warehouse_id=wh["id"],
                            sku=prod["sku"],
                            movement_type="Import",
                            quantity_change=quantity,
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
        from .contracts import EngineContract

        EngineContract.verify(plan)
        cfg = plan["config_snapshot"]
        from ..config.profiles import ENGINE_VERSION, ParameterProfiles

        if plan.get("engine_version", 1) != ENGINE_VERSION:
            raise ValueError(
                "Job dùng engine cũ; cần hoàn tất bằng phiên bản cũ hoặc lập kế hoạch mới, không resume ngầm bằng engine mới."
            )
        seed = plan["seed"]
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
            "GST-04": 11,
            "CUS-08": 11,
            "SUP-01": 12,
            "SUP-02": 12,
            "WH-04": 13,
            "PAY-02": 14,
            "CAR-05": 11,
            "CAR-06": 11,
            "FIN-REC-01": 12,
            "FIN-REC-02": 13,
            "FIN-PAY-01": 14,
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
                cfg.items(),
                key=lambda item: (
                    item[1].get("phase", priority.get(item[0], 12)),
                    item[0],
                ),
            ):
                if not entry.get("enabled"):
                    continue
                automatic = entry.get("mode") == "all"
                count = entry.get("special", {}).get(day["day"], entry.get("count", 0))
                requested += count if not automatic else 0
                registry = {
                    a["code"]: a
                    for group in self.s.action_catalog(plan.get("entity_profile") or {})
                    for a in group["actions"]
                }
                defaults = {
                    f["key"]: f.get("default") for f in registry[code]["fields"]
                }
                index = 0
                exhausted = 0
                sweep = (
                    len(entry.get("variants", []))
                    if entry.get("variant_mode") == "cycle"
                    else 1
                )
                sweep = max(1, sweep)
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
                    # Stages preserve causality; stable within-stage spreading avoids one timestamp for all commands.
                    from datetime import datetime, timedelta

                    stage = (
                        int(code[-2:]) - 1
                        if code.startswith(("GST-WEB-", "CUS-WEB-"))
                        else 0
                    )
                    second = int(aid[:8], 16) % (
                        600 if code.startswith(("GST-WEB-", "CUS-WEB-")) else 3600
                    )
                    at = (
                        datetime.fromisoformat(day["day"])
                        + timedelta(
                            hours=8 + priority.get(code, 12),
                            minutes=stage * 10,
                            seconds=second,
                        )
                    ).isoformat(timespec="seconds")
                    if entry.get("schedule"):
                        from ..config.configuration import ActionSchedule

                        at = ActionSchedule.at(day["day"], entry["schedule"], seed, aid)
                    params, profile = ParameterProfiles.resolve(
                        entry, defaults, seed, aid, index
                    )
                    params["_delay_days"] = entry.get("delay_days", 0)
                    action = {
                        "parameter_rules": entry.get("parameter_rules", []),
                        "preferences": entry.get("preferences", {}),
                        "automatic": automatic,
                        "actor_pool": entry.get("actor_pool"),
                        "selection": entry.get("selection", {}),
                        "timing": entry.get("schedule", {}),
                        "profile": profile,
                        "seed": seed,
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
                        exhausted = (
                            exhausted + 1 if receipt["status"] == "EXHAUSTED" else 0
                        )
                        if automatic and exhausted >= sweep:
                            break
                        continue
                    job.update(
                        day=day["day"],
                        heartbeat=stamp(),
                        message=f"{code} · {ACTIONS[code]['label']}",
                    )
                    self.db.put("jobs", jid, job)

                    def apply(u):
                        from ..infrastructure.storage import RuntimeState

                        state = RuntimeState(self.db)
                        engine = DomainEngine(
                            self.db,
                            u,
                            {
                                **action,
                                "entity_profile": plan.get("entity_profile"),
                                "business_policy": plan.get("business_policy"),
                                "schedule": {
                                    k: v.get("delay_days", 0) for k, v in cfg.items()
                                },
                            },
                            state,
                        )
                        engine.execute()
                        for change in u.changes:
                            row = change.get("after") or {}
                            if change["table"] == "page_events":
                                engine.meta(
                                    "session_last:" + str(row["session_id"]),
                                    row["event_time"],
                                )
                        return {
                            "effects": engine.effects,
                            "message": code,
                            "actor": engine.binding.execution_record(),
                            "resolved_params": dict(engine.p),
                            "selected_ids": {
                                name: row.get("id")
                                for name, row in getattr(
                                    engine, "selected_context", {}
                                ).items()
                            },
                            "effective_at": engine.now,
                        }

                    try:
                        result = self.transact(key, apply)
                        exhausted = 0
                        self.db.put(
                            "action_results",
                            key,
                            {
                                "job": jid,
                                **action,
                                "actor": result.get("actor"),
                                "resolved_params": result.get("resolved_params"),
                                "selected_ids": result.get("selected_ids", {}),
                                "at": result.get("effective_at") or action["at"],
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
                            exhausted += 1
                            if exhausted >= sweep:
                                break
                            continue
                        job["rejected"] = job.get("rejected", 0) + 1
                    self.db.put("jobs", jid, job)
                    pause = float(job["payload"].get("delay_ms", 0)) / 1000
                    if pause:
                        time.sleep(min(pause, 1))
            from ..diagnostics.validation import BusinessValidator

            report = BusinessValidator(self.db).report(job=jid)
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
            job = self.db.get("jobs", jid)
            if job["status"] not in ["QUEUED", "RUNNING"]:
                return False
            job["status"] = "RUNNING"
            job["heartbeat"] = stamp()
            self.db.put("jobs", jid, job)
            try:
                kind = job["kind"]
                from .operations import DataOperations

                complete = (
                    DataOperations(self.s).reset(self, jid, job)
                    if kind == "reset"
                    else self.sync(jid, job)
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
