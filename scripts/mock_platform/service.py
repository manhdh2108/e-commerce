from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from collections import Counter
import json
from pathlib import Path
import sqlite3
import uuid
from sqlalchemy import select, inspect
from .storage import Database, UnitOfWork, clean, ROOT

CATALOG = json.loads((Path(__file__).parent / "actions.json").read_text())
ACTIONS = {a["code"]: {**a, "system": s["key"]} for s in CATALOG for a in s["actions"]}


class ConfigurationConflict(ValueError):
    """A saved configuration changed since it was opened."""


def uid():
    return str(uuid.uuid4())


def stamp():
    return (
        datetime.now(ZoneInfo("Asia/Bangkok"))
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def days(start, end):
    start = date.fromisoformat(start)
    end = date.fromisoformat(end)
    if start > end:
        raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi.")
    if (end - start).days > 366:
        raise ValueError("Mỗi lượt tối đa 367 ngày; có thể chạy tiếp lượt sau.")
    return [
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    ]


class PlatformService:
    def __init__(self, db=None):
        self.db = db or Database()

    def setup(self):
        return self.db.get("settings", "main", {})

    def summary(self):
        settings = self.setup()
        counts = {}
        ready = False
        try:
            ready = "products" in inspect(self.db.business).get_table_names()
            if ready:
                with self.db.business.connect() as c:
                    for name, t in self.db.bm.tables.items():
                        counts[name] = c.execute(
                            select(__import__("sqlalchemy").func.count()).select_from(t)
                        ).scalar()
        except Exception:
            pass
        jobs = sorted(
            self.db.list("jobs"), key=lambda r: r.get("created_at", ""), reverse=True
        )
        last = self.db.get("checkpoint", "main", {}).get("last_day")
        nextday = (
            (date.fromisoformat(last) + timedelta(days=1)).isoformat()
            if last
            else settings.get("start_date")
        )
        return {
            "default_source": str(ROOT / "data/tiki_crawl.db"),
            "settings": {k: v for k, v in settings.items() if k != "password"},
            "ready": ready,
            "counts": counts,
            "last_day": last,
            "next_day": nextday,
            "jobs": jobs[:30],
            "target": str(self.db.business.url.render_as_string(hide_password=True)),
            "control": str(self.db.control.url.render_as_string(hide_password=True)),
        }

    def prepare(self, p):
        start = p.get("start_date")
        date.fromisoformat(start)
        if self.setup() and self.setup().get("start_date") != start:
            raise ValueError(
                "Ngày bắt đầu đã cố định. Dùng môi trường mới để thay lịch sử."
            )
        source = (
            Path(p.get("source", str(ROOT / "data/tiki_crawl.db")))
            .expanduser()
            .resolve()
        )
        if not source.is_file():
            raise ValueError("Không tìm thấy database crawler.")
        with self.db.writer():
            if self.setup() and self.setup().get("seed") != int(p.get("seed", 42)):
                raise ValueError("Seed đã cố định cho môi trường này.")
            if any(
                j["status"] not in ["COMPLETE", "CANCELLED"]
                for j in self.db.list("jobs")
            ):
                raise ValueError(
                    "Cần hoàn tất tác vụ còn dang dở trước khi đổi thiết lập."
                )
            actual_tables = set(inspect(self.db.business).get_table_names())
            unknown = actual_tables - set(self.db.bm.tables)
            if unknown:
                raise ValueError(
                    "DB nghiệp vụ có bảng ngoài mô hình; chọn DB riêng, không tự sửa dữ liệu đang có."
                )
            for name in actual_tables:
                actual_columns = {
                    col["name"] for col in inspect(self.db.business).get_columns(name)
                }
                if actual_columns != set(self.db.bm.tables[name].c.keys()):
                    raise ValueError(
                        f"Cấu trúc bảng {name} không tương thích. Không tự migrate dữ liệu cũ."
                    )
            self.db.bm.create_all(self.db.business)
            self.db.put(
                "settings",
                "main",
                {
                    "start_date": start,
                    "seed": int(p.get("seed", 42)),
                    "source": str(source),
                    "timezone": "Asia/Bangkok",
                    "schema_version": 1,
                },
            )
        return self.summary()

    def validate_config(self, config):
        if not isinstance(config, dict):
            raise ValueError("Cấu hình không hợp lệ.")
        for code, cfg in config.items():
            if code not in ACTIONS:
                raise ValueError("Mã hành động không tồn tại.")
            if not isinstance(cfg, dict):
                raise ValueError("Cấu hình hành động phải là object.")
            for n in [cfg.get("count", 0), *cfg.get("special", {}).values()]:
                if type(n) is not int or n < 0 or n > 10000:
                    raise ValueError("Số lần phải là số nguyên từ 0 tới 10.000.")
            for day in cfg.get("special", {}):
                date.fromisoformat(day)
            if cfg.get("enabled") and not ACTIONS[code]["available"]:
                raise ValueError(f"{code}: {ACTIONS[code]['unavailable_reason']}")
            if cfg.get("enabled"):
                params = cfg.get("params", {})
                if code == "CAT-04" and (
                    not params.get("target") or not str(params.get("value", "")).strip()
                ):
                    raise ValueError("CAT-04: cần chọn ID danh mục và nhập tên mới.")
                if code in ["SEL-08", "FIN-POL-01"] and not params.get("category"):
                    raise ValueError(f"{code}: cần nhập ID danh mục đích.")
            if cfg.get("mode", "count") not in ["count", "all"]:
                raise ValueError("Chế độ xử lý không hợp lệ.")
            if cfg.get("mode") == "all" and not ACTIONS[code].get("supports_auto"):
                raise ValueError(f"{code}: hành động không hỗ trợ chế độ theo đầu vào.")
            allowed = {f["key"]: f for f in ACTIONS[code]["fields"]}
            for key, value in cfg.get("params", {}).items():
                if key not in allowed:
                    raise ValueError(f"{code}: trường không được hỗ trợ {key}")
                f = allowed[key]
                if value in ["", None]:
                    continue
                if f["type"] == "number" and (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or value < f.get("min", 0)
                    or value > f.get("max", 10**12)
                ):
                    raise ValueError(f"{code}: {f['label']} ngoài miền hợp lệ.")
                if f["type"] == "select" and value not in f["options"]:
                    raise ValueError(f"{code}: lựa chọn không hợp lệ.")
                if f["type"] == "date":
                    date.fromisoformat(value)

        def active(code):
            return config.get(code, {}).get("enabled", False)

        if active("VIS-01") and any(
            active(code) for code in ["GST-WEB-03", "CUS-WEB-03"]
        ):
            raise ValueError(
                "Lượt xem sản phẩm đang có hai nguồn: chọn VIS-01 hoặc các hành động xem ở Analytics, không bật cả hai."
            )
        return config

    def save_version(self, p):
        cfg = self.validate_config(p.get("config", {}))
        id = uid()
        self.db.put(
            "versions",
            id,
            {
                "name": p.get("name") or f"Kịch bản {stamp()}",
                "config": cfg,
                "created_at": stamp(),
                "revision": 1,
            },
        )
        return {"id": id, "revision": 1}

    def update_version(self, id, p):
        if "config" not in p:
            raise ValueError("Thiếu nội dung cấu hình. Thay đổi chưa được lưu.")
        cfg = clean(self.validate_config(p.get("config", {})))
        expected = p.get("revision")
        if type(expected) is not int:
            raise ValueError(
                "Thiếu thông tin lần lưu. Hãy tải lại cấu hình trước khi sửa."
            )
        with self.db.control.begin() as connection:
            row = connection.execute(
                select(self.db.records.c.data)
                .where(self.db.records.c.kind == "versions", self.db.records.c.id == id)
                .with_for_update()
            ).first()
            if not row:
                raise ValueError("Không tìm thấy cấu hình đã lưu.")
            old = row[0]
            revision = old.get("revision", 1)
            if expected != revision:
                raise ConfigurationConflict(
                    "Cấu hình đã được sửa ở nơi khác. Hãy tải lại bản mới nhất; thay đổi đang nhập chưa bị mất."
                )
            name = p.get("name", old["name"])
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Tên cấu hình không được để trống.")
            name = name.strip()
            if name == old["name"] and cfg == old["config"]:
                return {"id": id, "revision": revision, "changed": False}
            # Freeze legacy plans before editing the shared saved configuration.
            plans = connection.execute(
                select(self.db.records).where(self.db.records.c.kind == "plans")
            ).all()
            for plan_row in plans:
                plan = plan_row.data
                if plan.get("version") == id and "config_snapshot" not in plan:
                    self.db.put(
                        "plans",
                        plan_row.id,
                        {
                            **plan,
                            "config_snapshot": old["config"],
                            "version_revision": revision,
                            "version_name": old["name"],
                        },
                        connection,
                    )
            self.db.put(
                "version_history",
                f"{id}:{revision}",
                {**old, "revision": revision},
                connection,
            )
            self.db.put(
                "versions",
                id,
                {
                    **old,
                    "name": name,
                    "config": cfg,
                    "revision": revision + 1,
                    "updated_at": stamp(),
                },
                connection,
            )
        return {"id": id, "revision": revision + 1, "changed": True}

    def execution_plan(self, id):
        """Read or freeze a legacy plan atomically with saved-config edits."""
        with self.db.control.begin() as connection:
            plan = self.db.get("plans", id, conn=connection)
            if not plan:
                raise ValueError("Không tìm thấy kế hoạch chạy.")
            version_row = connection.execute(
                select(self.db.records.c.data)
                .where(
                    self.db.records.c.kind == "versions",
                    self.db.records.c.id == plan["version"],
                )
                .with_for_update()
            ).first()
            # An edit may have frozen this plan while we waited for its lock.
            plan = self.db.get("plans", id, conn=connection)
            if "config_snapshot" not in plan:
                version = version_row[0]
                plan = {
                    **plan,
                    "config_snapshot": version["config"],
                    "version_revision": version.get("revision", 1),
                    "version_name": version["name"],
                }
                self.db.put("plans", id, plan, connection)
            return plan

    def draft(self, p):
        cfg = self.validate_config(p["config"])
        self.db.put("draft", "main", cfg)
        return {"saved": True}

    def plan(self, p):
        overview = self.summary()
        if not overview["ready"] or not overview["next_day"]:
            raise ValueError("Hãy chuẩn bị môi trường ở Thiết lập trước.")
        if p["start"] != overview["next_day"]:
            raise ValueError(
                f"Phải bắt đầu từ {overview['next_day']}; không được bỏ qua hoặc chạy lại ngày."
            )
        version = self.db.get("versions", p["version"])
        if not version:
            raise ValueError("Hãy lưu phiên bản cấu hình trước khi preview.")
        rows = []
        total = 0
        for day in days(p["start"], p["end"]):
            actions = []
            for code, cfg in version["config"].items():
                if not cfg.get("enabled"):
                    continue
                automatic = cfg.get("mode") == "all"
                n = (
                    0
                    if automatic
                    else cfg.get("special", {}).get(day, cfg.get("count", 0))
                )
                total += n
                if n or automatic:
                    actions.append(
                        {
                            "code": code,
                            "label": ACTIONS[code]["label"],
                            "system": ACTIONS[code]["system"],
                            "requested": "Theo đầu vào" if automatic else n,
                        }
                    )
            rows.append(
                {
                    "day": day,
                    "actions": actions,
                    "total": sum(
                        a["requested"]
                        for a in actions
                        if isinstance(a["requested"], int)
                    ),
                    "automatic": sum(a["requested"] == "Theo đầu vào" for a in actions),
                }
            )
        if total > 100000:
            raise ValueError(
                "Bản local giới hạn 100.000 hành động/lượt; chia nhỏ khoảng hoặc giảm số lượng."
            )
        id = uid()
        plan = {
            "version": p["version"],
            "version_revision": version.get("revision", 1),
            "config_snapshot": clean(version["config"]),
            "version_name": version["name"],
            "start": p["start"],
            "end": p["end"],
            "days": rows,
            "total": total,
            "revision": self.db.get("revision", "main", 0),
            "created_at": stamp(),
            "warning": "Số yêu cầu không bảo đảm thành công; điều kiện được kiểm tra tại thời điểm chạy. Preview không ghi dữ liệu nghiệp vụ.",
        }
        self.db.put("plans", id, plan)
        return {"id": id, **plan}

    def source_preview(self, p, persist=True):
        settings = self.setup()
        if not settings:
            raise ValueError("Chuẩn bị môi trường trước khi đồng bộ.")
        limit = int(p.get("limit", 0))
        if limit < 0:
            raise ValueError("Giới hạn không được âm.")
        path = Path(settings["source"])
        uri = path.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as c:
            c.row_factory = sqlite3.Row
            c.execute("BEGIN")
            products = [
                dict(r) for r in c.execute("SELECT * FROM products ORDER BY id")
            ]
            raw = {
                r["product_id"]: json.loads(r["raw_json"])
                for r in c.execute("SELECT * FROM product_raw")
            }
            memberships = {}
            for row in c.execute(
                "SELECT * FROM product_categories ORDER BY leaf_category_id"
            ):
                memberships.setdefault(row["product_id"], []).append(dict(row))
        with self.db.business.connect() as c:
            u = UnitOfWork(self.db, c)
            existing_rows = {r["id"]: r for r in u.rows("products")}
            existing = set(existing_rows)
            skus = {r["sku"] for r in u.rows("products")}
        new = []
        errors = []
        skipped = 0
        deferred = 0
        source_skus = Counter(str(p.get("sku")) for p in products if p.get("sku"))
        for prod in products:
            if prod["id"] in existing:
                previous = existing_rows[prod["id"]]
                if str(previous.get("seller_id")) != str(prod.get("seller_id")) or str(
                    previous.get("seller_product_id")
                ) != str(prod.get("seller_product_id")):
                    errors.append(
                        {
                            "id": prod["id"],
                            "reason": "Cùng ID nhưng khác seller/chào bán; bỏ qua, giữ bản ghi cũ.",
                        }
                    )
                else:
                    skipped += 1
                continue
            sku = prod.get("sku")
            leafs = memberships.get(prod["id"], [])
            if (
                not sku
                or sku in skus
                or source_skus[str(sku)] > 1
                or type(prod.get("seller_id")) is not int
                or prod.get("seller_id", 0) <= 0
                or not prod.get("name")
                or not prod.get("price")
                or prod["price"] <= 0
                or not leafs
            ):
                errors.append(
                    {
                        "id": prod["id"],
                        "reason": "Thiếu/trùng SKU, thiếu seller/tên/giá hợp lệ hoặc danh mục lá.",
                    }
                )
                continue
            if limit and len(new) >= limit:
                deferred += 1
                continue
            prod["leaf_id"] = leafs[0]["leaf_category_id"]
            prod["root_id"] = leafs[0]["root_category_id"]
            prod["raw"] = raw.get(prod["id"], {})
            skus.add(sku)
            new.append(prod)
        new_active = p.get("new_active", True)
        if type(new_active) is not bool:
            raise ValueError("Trạng thái mở bán mới phải là boolean.")
        snapshot = {
            "new_active": new_active,
            "products": new,
            "skipped": skipped,
            "deferred": deferred,
            "errors": errors,
            "source_count": len(products),
            "source_existing": sum(prod["id"] in existing for prod in products),
            "source_new": sum(prod["id"] not in existing for prod in products),
            "revision": self.db.get("revision", "main", 0),
            "created_at": stamp(),
        }
        id = uid()
        if persist:
            self.db.put("sync_previews", id, snapshot)
        return {
            "id": id,
            **{k: v for k, v in snapshot.items() if k != "products"},
            "new": len(new),
            "sample": [
                {k: r.get(k) for k in ["id", "name", "price", "seller_id"]}
                for r in new[:8]
            ],
        }

    def newjob(self, kind, p):
        key = p.get("request_key")
        if not key:
            raise ValueError("Thiếu khóa chống gửi lặp.")
        old = next(
            (j for j in self.db.list("jobs") if j.get("request_key") == key), None
        )
        if old:
            return old
        with self.db.writer():
            if any(
                j["status"]
                in (
                    ["QUEUED", "RUNNING", "PAUSING"]
                    if kind == "reset"
                    else [
                        "QUEUED",
                        "RUNNING",
                        "PAUSING",
                        "PAUSED",
                        "FAILED",
                        "INTERRUPTED",
                    ]
                )
                for j in self.db.list("jobs")
            ):
                raise ValueError(
                    "Còn tác vụ đang chạy hoặc dang dở. Hãy hoàn tất/tiếp tục tác vụ đó trước khi tạo tác vụ mới."
                )
            if kind == "bootstrap" and self.db.get("lifecycle", "reset", False):
                if not self.data("products"):
                    raise ValueError(
                        "Hãy đồng bộ sản phẩm từ SQLite trước khi tạo dữ liệu nền."
                    )
            if kind == "reset":
                from .operations import DataOperations

                DataOperations(self).validate_reset(p)
            if kind == "run":
                if self.db.get("lifecycle", "reset", False) and not self.db.get(
                    "bootstrap", "done"
                ):
                    raise ValueError(
                        "Hãy đồng bộ catalog và tạo dữ liệu nền trước khi mô phỏng."
                    )
                delay = p.get("delay_ms", 0)
                if (
                    not isinstance(delay, (int, float))
                    or isinstance(delay, bool)
                    or not 0 <= delay <= 1000
                ):
                    raise ValueError("Độ chậm phải từ 0 tới 1.000 ms.")
                plan = self.db.get("plans", p.get("plan"))
                if (
                    not plan
                    or plan["revision"] != self.db.get("revision", "main", 0)
                    or plan["start"] != self.summary()["next_day"]
                    or plan.get("version_revision", 1)
                    != self.db.get("versions", plan["version"], {}).get("revision", 1)
                ):
                    raise ValueError("Kế hoạch hết hiệu lực; hãy preview lại.")
            if kind == "sync":
                preview = self.db.get("sync_previews", p.get("preview"))
                if not preview or preview["revision"] != self.db.get(
                    "revision", "main", 0
                ):
                    raise ValueError("Preview đồng bộ hết hiệu lực.")
            id = uid()
            job = {
                "kind": kind,
                "status": "QUEUED",
                "created_at": stamp(),
                "payload": p,
                "request_key": key,
                "completed": 0,
                "rejected": 0,
                "message": "Đang chờ worker",
                "day": None,
            }
            self.db.put("jobs", id, job)
            return {"id": id, **job}

    def command(self, id, command):
        job = self.db.get("jobs", id)
        if not job:
            raise ValueError("Không tìm thấy job.")
        if command == "pause":
            if job["kind"] == "reset":
                raise ValueError(
                    "Xóa toàn bộ là một transaction; không hỗ trợ tạm dừng giữa chừng."
                )
            if job["status"] not in ["RUNNING", "QUEUED"]:
                raise ValueError("Chỉ tạm dừng job đang chạy/chờ.")
            self.db.put("commands", id, {"pause": True})
        elif command == "resume":
            if job["status"] not in ["PAUSED", "FAILED", "INTERRUPTED"]:
                raise ValueError("Job chưa ở trạng thái có thể tiếp tục.")
            if any(
                j["id"] != id and j["status"] in ["RUNNING", "QUEUED"]
                for j in self.db.list("jobs")
            ):
                raise ValueError("Đã có job khác.")
            self.db.put("commands", id, {"pause": False})
            job["status"] = "QUEUED"
            self.db.put("jobs", id, job)
        return {"accepted": True}

    def data(self, table, offset=0):
        if table not in self.db.bm.tables:
            raise ValueError("Bảng không hợp lệ.")
        t = self.db.bm.tables[table]
        with self.db.business.connect() as c:
            return clean(
                [
                    dict(r)
                    for r in c.execute(
                        select(t).order_by(t.c.id).offset(offset).limit(50)
                    ).mappings()
                ]
            )
