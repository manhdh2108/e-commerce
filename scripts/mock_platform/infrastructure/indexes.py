"""Optional index-only migration; preserves every business row and identifier.

python -m scripts.mock_platform.infrastructure.indexes           # preview
python -m scripts.mock_platform.infrastructure.indexes --apply   # wait for active writers first
"""

import argparse
import json

from sqlalchemy import Index, inspect

INDEXES = {
    "page_events": [("session_id", "event_type")],
    "sessions": [("ended_at", "customer_id")],
    "cart_items": [("session_id", "cart_status")],
    "orders": [("order_status", "created_at"), ("customer_id",), ("seller_id",)],
    "payments": [("order_id", "payment_status")],
    "inventory_levels": [("sku",)],
    "inventory_movements": [("warehouse_id", "sku")],
    "returns": [("order_item_id", "status")],
    "refunds": [("refund_status", "requested_at")],
}


def attach_indexes(metadata):
    for name, groups in INDEXES.items():
        table = metadata.tables[name]
        for columns in groups:
            label = "ix_mock_" + name + "_" + "_".join(columns)
            if not any(i.name == label for i in table.indexes):
                Index(label, *(table.c[c] for c in columns))


def migrate(db, apply=False):
    with db.writer(), db.business.begin() as c:
        inspector = inspect(c)
        changes = []
        for name in INDEXES:
            if not inspector.has_table(name):
                raise ValueError("Cần chuẩn bị schema trước khi tạo index.")
            existing = {i["name"] for i in inspector.get_indexes(name)}
            for index in sorted(db.bm.tables[name].indexes, key=lambda i: i.name):
                if index.name.startswith("ix_mock_") and index.name not in existing:
                    changes.append(index.name)
                    if apply:
                        index.create(c)
        return {"applied": apply, "indexes": changes, "business_rows_modified": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from .storage import Database

    print(json.dumps(migrate(Database(), args.apply), ensure_ascii=False, indent=2))
