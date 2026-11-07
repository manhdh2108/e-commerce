from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Numeric,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    select,
    insert,
    update,
    text,
    JSON,
)
from sqlalchemy.types import TypeDecorator

ROOT = Path(__file__).resolve().parents[2]


_PLAIN = (str, int, float, bool, type(None))


def _clean_scalar(x):
    if isinstance(x, _PLAIN):
        return x
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    raise TypeError


def clean(value):
    # Fast path for flat rows of scalars; identical to the JSON round trip below.
    if isinstance(value, dict) and all(type(k) is str for k in value):
        try:
            return {k: _clean_scalar(v) for k, v in value.items()}
        except TypeError:
            pass
    return json.loads(
        json.dumps(
            value,
            default=lambda x: float(x) if isinstance(x, Decimal) else x.isoformat(),
        )
    )


class ISODate(TypeDecorator):
    impl = Date
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return date.fromisoformat(value) if isinstance(value, str) else value

    def process_result_value(self, value, dialect):
        return value.isoformat() if value else value


class ISOTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return datetime.fromisoformat(value) if isinstance(value, str) else value

    def process_result_value(self, value, dialect):
        return value.isoformat() if value else value


class Database:
    def __init__(self, control_url=None, business_url=None):
        self.control_url = control_url or os.getenv(
            "MOCK_CONTROL_URL",
            "postgresql+psycopg://mock:local_mock_only@127.0.0.1:55432/mock_control",
        )
        self.business_url = business_url or os.getenv(
            "MOCK_BUSINESS_URL",
            "postgresql+psycopg://mock:local_mock_only@127.0.0.1:55432/mock_oltp",
        )
        self.control = create_engine(self.control_url)
        self.business = create_engine(self.business_url)
        c, b = self.control.url, self.business.url
        if c.database == b.database:
            raise ValueError(
                "Control DB và Business DB phải là hai database khác nhau."
            )
        self.cm = MetaData()
        self.records = Table(
            "control_records",
            self.cm,
            Column("kind", String, primary_key=True),
            Column("id", String, primary_key=True),
            Column("data", JSON, nullable=False),
        )
        self.bm = MetaData()
        fields = json.loads(
            (Path(__file__).parent / "business_schema.json").read_text()
        )
        types = {
            "int": Integer,
            "bigint": BigInteger().with_variant(Integer, "sqlite"),
            "varchar": String,
            "text": Text,
            "decimal": Numeric(24, 6),
            "boolean": Boolean,
            "date": ISODate,
            "timestamp": ISOTime,
        }
        fks = {("categories", "parent_id"): "categories.id"}
        refs = {
            "customer_id": "customers.id",
            "seller_id": "sellers.id",
            "category_id": "categories.id",
            "product_id": "products.id",
            "order_id": "orders.id",
            "order_item_id": "order_items.id",
            "warehouse_id": "warehouses.id",
            "carrier_id": "carriers.id",
            "promotion_id": "promotions.id",
            "shipping_promotion_id": "promotions.id",
            "session_id": "sessions.id",
            "campaign_id": "marketing_campaigns.id",
            "channel_id": "channels.id",
            "payment_method_id": "payment_methods.id",
            "shipping_address_id": "customer_addresses.id",
        }
        for name, cols in fields.items():
            self_table = []
            for col in cols:
                n = col["name"]
                fk = fks.get((name, n), refs.get(n))
                args = [ForeignKey(fk)] if fk else []
                self_table.append(
                    Column(
                        n,
                        types[col["type"]],
                        *args,
                        primary_key=n == "id",
                        nullable=n != "id",
                    )
                )
            unique = {
                "products": [("sku",)],
                "orders": [("order_code",)],
                "shipments": [("tracking_code",), ("order_code",)],
                "inventory_levels": [("warehouse_id", "sku")],
                "inventory_daily_balance": [("balance_date", "warehouse_id", "sku")],
                "product_reviews": [("order_item_id",)],
                "seller_payouts": [("seller_id", "period_start", "period_end")],
                "ad_spend_logs": [("campaign_id", "channel_code", "log_date")],
            }
            self_table += [UniqueConstraint(*cols) for cols in unique.get(name, [])]
            Table(name, self.bm, *self_table)
        if b.drivername.startswith("sqlite"):
            from sqlalchemy import event

            event.listen(
                self.business,
                "connect",
                lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"),
            )

    def start_control(self):
        self.cm.create_all(self.control)

    def get(self, kind, key, default=None, conn=None):
        if conn is None:
            with self.control.connect() as c:
                return self.get(kind, key, default, c)
        row = conn.execute(
            select(self.records.c.data).where(
                self.records.c.kind == kind, self.records.c.id == str(key)
            )
        ).first()
        return row[0] if row else default

    def put(self, kind, key, value, conn=None):
        if conn is None:
            with self.control.begin() as c:
                return self.put(kind, key, value, c)
        t = self.records
        where = (t.c.kind == kind) & (t.c.id == str(key))
        if conn.execute(select(t.c.id).where(where)).first():
            conn.execute(update(t).where(where).values(data=clean(value)))
        else:
            conn.execute(insert(t).values(kind=kind, id=str(key), data=clean(value)))

    def list(self, kind):
        with self.control.connect() as c:
            return [
                {"id": r.id, **r.data}
                for r in c.execute(
                    select(self.records).where(self.records.c.kind == kind)
                )
            ]

    @contextmanager
    def writer(self):
        with self.business.connect() as c:
            pg = c.dialect.name == "postgresql"
            if pg:
                ok = c.execute(text("SELECT pg_try_advisory_lock(746219005)")).scalar()
                c.commit()
                if not ok:
                    raise ValueError(
                        "Môi trường đang có tác vụ ghi. Vui lòng chờ hoặc tạm dừng."
                    )
            try:
                yield
            finally:
                if pg:
                    c.execute(text("SELECT pg_advisory_unlock(746219005)"))
                    c.commit()


class SharedTableCache:
    """Committed full-table images reused across transactions of one writer.

    Only the single business writer (worker, under the advisory lock) uses it.
    A transaction reads a private copy; its images are merged back only after
    the business commit, so a rollback leaves the shared copy untouched.
    """

    def __init__(self):
        self.tables = {}

    def clear(self):
        self.tables = {}

    def merge(self, uow):
        for name, rows in uow.cache.items():
            positions = uow.positions.get(name)
            if any(rows[i]["id"] > rows[i + 1]["id"] for i in range(len(rows) - 1)):
                rows = sorted(rows, key=lambda r: r["id"])
                positions = None
            if positions is None:
                positions = {r["id"]: i for i, r in enumerate(rows)}
            self.tables[name] = (rows, positions)
        # Tables changed in this transaction but not read through rows():
        # apply the committed after-images to the shared copy.
        for change in uow.changes:
            name = change["table"]
            if name in uow.cache or name not in self.tables:
                continue
            rows, positions = self.tables[name]
            after, position = change["after"], positions.get(change["id"])
            if after is None:
                self.tables.pop(name)
            elif position is not None:
                rows[position] = after
            elif not rows or rows[-1]["id"] < after["id"]:
                positions[after["id"]] = len(rows)
                rows.append(after)
            else:
                self.tables.pop(name)


class UnitOfWork:
    """Collect before/after images; cache reads within one transaction.

    With ``shared`` (a SharedTableCache), full-table reads start from the last
    committed image instead of reloading the table.
    """

    def __init__(self, db, conn, shared=None):
        self.db, self.conn = db, conn
        self.shared = shared
        self.changes = []
        self.cache = {}

    def rows(self, name):
        if name not in self.cache:
            image = self.shared.tables.get(name) if self.shared else None
            if image is not None and not any(
                c["table"] == name for c in self.changes
            ):
                self.cache[name] = list(image[0])
                self.positions[name] = dict(image[1])
                return self.cache[name]
            t = self.db.bm.tables[name]
            self.cache[name] = [
                clean(dict(r))
                for r in self.conn.execute(select(t).order_by(t.c.id)).mappings()
            ]
        return self.cache[name]

    def one(self, name, id):
        if name in self.cache:
<<<<<<< Updated upstream:scripts/mock_platform/storage.py
            return next((r for r in self.cache[name] if r["id"] == id), None)
=======
            if name not in self.positions:
                self.positions[name] = {
                    r["id"]: i for i, r in enumerate(self.cache[name])
                }
            position = self.positions[name].get(id)
            return self.cache[name][position] if position is not None else None
        image = self.shared.tables.get(name) if self.shared else None
        if (
            image is not None
            and type(id) is int
            and (name, id) not in self.row_cache
            and not any(c["table"] == name for c in self.changes)
        ):
            position = image[1].get(id)
            return image[0][position] if position is not None else None
        if (name, id) not in self.row_cache:
            t = self.db.bm.tables[name]
            r = self.conn.execute(select(t).where(t.c.id == id)).mappings().first()
            self.row_cache[name, id] = clean(dict(r)) if r else None
        return self.row_cache[name, id]

    def prefetch_by(self, name, column, values):
>>>>>>> Stashed changes:scripts/mock_platform/infrastructure/storage.py
        t = self.db.bm.tables[name]
        r = self.conn.execute(select(t).where(t.c.id == id)).mappings().first()
        return clean(dict(r)) if r else None

    def refresh_row(self, name, id):
        t = self.db.bm.tables[name]
        r = self.conn.execute(select(t).where(t.c.id == id)).mappings().first()
        after = clean(dict(r)) if r else None
        if name in self.cache:
            self.cache[name] = [r for r in self.cache[name] if r["id"] != id]
            if after is not None:
                self.cache[name].append(after)
                self.cache[name].sort(key=lambda r: r["id"])
        return after

    def add(self, table_name, **values):
        from sqlalchemy import func

        t = self.db.bm.tables[table_name]
        if "id" not in values:
            values["id"] = (
                self.conn.execute(select(func.max(t.c.id))).scalar() or 0
            ) + 1
        self.conn.execute(insert(t).values(**values))
        after = self.refresh_row(table_name, values["id"])
        self.changes.append(
            {"table": table_name, "id": values["id"], "before": None, "after": after}
        )
        return after

    def change(self, table_name, id, **values):
        t = self.db.bm.tables[table_name]
        before = self.one(table_name, id)
        if before is None:
            raise ValueError(f"Không tìm thấy {table_name} ID {id}.")
        self.conn.execute(update(t).where(t.c.id == id).values(**values))
        after = self.refresh_row(table_name, id)
        if before != after:
            self.changes.append(
                {"table": table_name, "id": id, "before": before, "after": after}
            )
        return after
<<<<<<< Updated upstream:scripts/mock_platform/storage.py
=======


class RuntimeState:
    """Read-through metadata snapshot for one command, without loading the full journal.

    ``shared`` (optional, worker-owned) maps key -> JSON text (or None when the
    record does not exist) for committed runtime records; values are decoded
    per command so callers always get fresh objects, as from the database.
    """

    def __init__(self, db, shared=None):
        self.db = db
        self.cache = {}
        self.shared = shared

    def prefetch(self, keys):
        missing = list(dict.fromkeys(k for k in keys if k not in self.cache))
        if self.shared is not None:
            rest = []
            for k in missing:
                if k in self.shared:
                    text = self.shared[k]
                    self.cache[k] = None if text is None else json.loads(text)
                else:
                    rest.append(k)
            missing = rest
        t = self.db.records
        if not missing:
            return
        with self.db.control.connect() as c:
            for start in range(0, len(missing), 500):
                part = missing[start : start + 500]
                self.cache.update(dict.fromkeys(part))
                for row in c.execute(
                    select(t.c.id, t.c.data).where(
                        t.c.kind == "runtime", t.c.id.in_(part)
                    )
                ):
                    self.cache[row.id] = row.data
        if self.shared is not None:
            for k in missing:
                v = self.cache[k]
                self.shared[k] = None if v is None else json.dumps(v)

    def get(self, key, default=None):
        if key not in self.cache:
            self.prefetch([key])
        value = self.cache[key]
        return default if value is None else value
>>>>>>> Stashed changes:scripts/mock_platform/infrastructure/storage.py
