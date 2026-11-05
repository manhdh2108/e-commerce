"""Explicit, additive schema migration. Opening the web never migrates old data."""

import argparse
import json

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn, AddConstraint, CreateIndex
from sqlalchemy import CheckConstraint, UniqueConstraint

from .storage import Database


class SchemaMigration:
    VERSION = 2

    def __init__(self, db):
        self.db = db

    def preflight(self, conn):
        inspector = inspect(conn)
        actual = set(inspector.get_table_names())
        unknown = actual - set(self.db.bm.tables)
        if unknown:
            raise ValueError("DB có bảng ngoài mô hình: " + ", ".join(sorted(unknown)))
        additions = []
        for name in sorted(actual):
            existing = {x["name"] for x in inspector.get_columns(name)}
            desired = set(self.db.bm.tables[name].c.keys())
            if existing - desired:
                raise ValueError(f"Bảng {name} có cột ngoài hợp đồng; không tự sửa.")
            for column in sorted(desired - existing):
                additions.append({"table": name, "column": column})
        constraints = []
        quote = conn.dialect.identifier_preparer.quote
        for name in sorted(actual):
            table = self.db.bm.tables[name]
            existing_checks = {r["name"] for r in inspector.get_check_constraints(name)}
            existing_unique = {
                tuple(r["column_names"]) for r in inspector.get_unique_constraints(name)
            }
            for constraint in table.constraints:
                if (
                    isinstance(constraint, CheckConstraint)
                    and constraint.name not in existing_checks
                ):
                    count = conn.exec_driver_sql(
                        f"SELECT count(*) FROM {quote(name)} WHERE NOT ({constraint.sqltext})"
                    ).scalar()
                    if count:
                        raise ValueError(
                            f"{name}: {count} dòng vi phạm {constraint.name}; không tự sửa dữ liệu."
                        )
                    constraints.append(
                        {"table": name, "name": constraint.name, "kind": "check"}
                    )
                if isinstance(constraint, UniqueConstraint):
                    fields = tuple(c.name for c in constraint.columns)
                    if fields not in existing_unique and set(fields).issubset(
                        {x["name"] for x in inspector.get_columns(name)}
                    ):
                        columns = ", ".join(quote(x) for x in fields)
                        count = conn.exec_driver_sql(
                            f"SELECT count(*) FROM (SELECT {columns} FROM {quote(name)} WHERE "
                            + " AND ".join(f"{quote(x)} IS NOT NULL" for x in fields)
                            + f" GROUP BY {columns} HAVING count(*) > 1) AS conflicts"
                        ).scalar()
                        if count:
                            raise ValueError(
                                f"{name}: khóa UNIQUE trùng {fields}; không tự sửa dữ liệu."
                            )
                        constraints.append(
                            {"table": name, "columns": list(fields), "kind": "unique"}
                        )
        if "customer_addresses" in actual:
            count = conn.exec_driver_sql(
                "SELECT count(*) FROM (SELECT customer_id FROM customer_addresses WHERE is_default AND customer_id IS NOT NULL GROUP BY customer_id HAVING count(*) > 1) AS conflicts"
            ).scalar()
            if count:
                raise ValueError(
                    "Khách có nhiều địa chỉ mặc định; cần kiểm tra trước migration."
                )
        return {
            "constraints": constraints,
            "version": self.VERSION,
            "new_tables": sorted(set(self.db.bm.tables) - actual),
            "new_columns": additions,
            "rewrites_existing_rows": False,
        }

    def preview(self):
        with self.db.business.connect() as conn:
            return self.preflight(conn)

    def apply(self):
        # Same lock as all business writes; no live worker may be mid-transaction.
        with self.db.writer():
            if any(
                j["status"]
                in ["QUEUED", "RUNNING", "PAUSING", "PAUSED", "FAILED", "INTERRUPTED"]
                for j in self.db.list("jobs")
            ):
                raise ValueError(
                    "Còn job dang dở. Hoàn tất bằng engine cũ hoặc chọn cặp DB test mới trước migration."
                )
            with self.db.business.begin() as conn:
                if conn.dialect.name == "postgresql":
                    conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
                    conn.exec_driver_sql("SET LOCAL statement_timeout = '120s'")
                report = self.preflight(conn)
                if conn.dialect.name != "postgresql" and (
                    report["constraints"] or report["new_columns"]
                ):
                    raise ValueError(
                        "Migration DB cũ yêu cầu PostgreSQL; SQLite dùng DB test mới."
                    )
                quote = conn.dialect.identifier_preparer.quote
                for item in report["new_columns"]:
                    column = self.db.bm.tables[item["table"]].c[item["column"]]
                    ddl = str(CreateColumn(column).compile(dialect=conn.dialect))
                    conn.execute(
                        text(f"ALTER TABLE {quote(item['table'])} ADD COLUMN {ddl}")
                    )
                self.db.bm.create_all(conn)
                if conn.dialect.name == "postgresql":
                    for item in report["constraints"]:
                        table = self.db.bm.tables[item["table"]]
                        constraint = next(
                            c
                            for c in table.constraints
                            if (
                                isinstance(c, CheckConstraint)
                                and c.name == item.get("name")
                            )
                            or (
                                isinstance(c, UniqueConstraint)
                                and [x.name for x in c.columns] == item.get("columns")
                            )
                        )
                        conn.execute(AddConstraint(constraint))
                    inspector = inspect(conn)
                    for table in self.db.bm.tables.values():
                        fks = {
                            tuple(r["constrained_columns"])
                            for r in inspector.get_foreign_keys(table.name)
                        }
                        for fk in table.foreign_key_constraints:
                            if tuple(c.name for c in fk.columns) not in fks:
                                conn.execute(AddConstraint(fk))
                    names = {
                        r["name"] for r in inspector.get_indexes("customer_addresses")
                    }
                    for index in self.db.bm.tables["customer_addresses"].indexes:
                        if index.name not in names:
                            conn.execute(CreateIndex(index))
                elif report["constraints"]:
                    # SQLite cannot ADD CONSTRAINT; new DB creation has all constraints.
                    raise ValueError(
                        "Migration constraint trên SQLite cần DB test mới; chưa hỗ trợ rebuild bảng."
                    )
            if (
                report["new_columns"]
                or report["new_tables"]
                or report["constraints"]
                or self.db.get("schema", "main", {}).get("version") != self.VERSION
            ):
                with self.db.control.begin() as control:
                    self.db.put("schema", "main", {"version": self.VERSION}, control)
                    settings = self.db.get("settings", "main", {}, control)
                    if settings:
                        self.db.put(
                            "settings",
                            "main",
                            {**settings, "schema_version": self.VERSION},
                            control,
                        )
                    self.db.put(
                        "revision",
                        "main",
                        self.db.get("revision", "main", 0, control) + 1,
                        control,
                    )
            return report


def main():
    parser = argparse.ArgumentParser(
        description="Preview migration mặc định; --apply mới ghi cấu trúc."
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = Database()
    if args.apply:
        db.start_control()
    migration = SchemaMigration(db)
    print(
        json.dumps(
            migration.apply() if args.apply else migration.preview(),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
