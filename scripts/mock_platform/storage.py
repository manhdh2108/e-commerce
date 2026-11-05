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
    CheckConstraint,
    Index,
    select,
    insert,
    update,
    text,
    JSON,
)
from sqlalchemy.types import TypeDecorator

ROOT = Path(__file__).resolve().parents[2]


def clean(value):
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
        self.control = create_engine(self.control_url, pool_pre_ping=True)
        self.business = create_engine(self.business_url, pool_pre_ping=True)
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
            "checkout_id": "checkouts.id",
            "cart_item_id": "cart_items.id",
            "return_id": "returns.id",
            "shipment_id": "shipments.id",
            "seller_payout_id": "seller_payouts.id",
            "commission_category_id": "categories.id",
        }
        checks = {
            "inventory_levels": [
                "quantity_on_hand >= 0 AND quantity_reserved >= 0 AND quantity_reserved <= quantity_on_hand"
            ],
            "inventory_daily_balance": [
                "quantity_on_hand >= 0 AND quantity_reserved >= 0 AND quantity_reserved <= quantity_on_hand"
            ],
            "order_items": [
                "quantity > 0 AND unit_price >= 0 AND discount_amount >= 0 AND net_amount >= 0"
            ],
            "orders": [
                "total_gross_amount >= 0 AND total_discount_amount >= 0 AND shipping_fee >= 0 AND shipping_discount_amount >= 0 AND final_amount >= 0"
            ],
            "payments": ["paid_amount >= 0"],
            "returns": ["quantity > 0 AND refund_amount >= 0"],
            "refunds": ["amount > 0"],
            "product_reviews": ["rating >= 1 AND rating <= 5"],
            "ad_spend_logs": [
                "cost_amount >= 0 AND clicks >= 0 AND impressions >= clicks"
            ],
            "seller_commission_rates": [
                "commission_rate >= 0 AND commission_rate <= 1"
            ],
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
                "checkouts": [("checkout_code",)],
                "delivery_attempts": [("shipment_id", "attempt_number")],
                "checkout_lines": [("cart_item_id",), ("order_item_id",)],
                "seller_payout_items": [("order_item_id",)],
                "orders": [("order_code",)],
                "order_items": [("order_id", "line_number")],
                "shipments": [("tracking_code",), ("order_code",)],
                "inventory_levels": [("warehouse_id", "sku")],
                "inventory_daily_balance": [("balance_date", "warehouse_id", "sku")],
                "product_reviews": [("order_item_id",)],
                "seller_payouts": [("seller_id", "period_start", "period_end")],
                "ad_spend_logs": [("campaign_id", "channel_code", "log_date")],
            }
            self_table += [UniqueConstraint(*cols) for cols in unique.get(name, [])]
            self_table += [
                CheckConstraint(expression, name=f"ck_mock_{name}_{i}")
                for i, expression in enumerate(checks.get(name, []))
            ]
            table = Table(name, self.bm, *self_table)
            if name == "customer_addresses":
                Index(
                    "uq_mock_customer_default",
                    table.c.customer_id,
                    unique=True,
                    postgresql_where=text("is_default AND customer_id IS NOT NULL"),
                    sqlite_where=text("is_default AND customer_id IS NOT NULL"),
                )
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


class UnitOfWork:
    """Collect before/after images; cache reads only within one transaction."""

    def __init__(self, db, conn):
        self.db, self.conn = db, conn
        self.changes = []
        self.cache = {}
        self.row_cache = {}

    def rows(self, name):
        if name not in self.cache:
            t = self.db.bm.tables[name]
            self.cache[name] = [
                clean(dict(r))
                for r in self.conn.execute(select(t).order_by(t.c.id)).mappings()
            ]
        return self.cache[name]

    def one(self, name, id):
        if name in self.cache:
            return next((r for r in self.cache[name] if r["id"] == id), None)
        if (name, id) not in self.row_cache:
            t = self.db.bm.tables[name]
            r = self.conn.execute(select(t).where(t.c.id == id)).mappings().first()
            self.row_cache[name, id] = clean(dict(r)) if r else None
        return self.row_cache[name, id]

    def refresh_row(self, name, id):
        t = self.db.bm.tables[name]
        r = self.conn.execute(select(t).where(t.c.id == id)).mappings().first()
        after = clean(dict(r)) if r else None
        self.row_cache[name, id] = after
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
