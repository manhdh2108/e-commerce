#!/usr/bin/env python3
"""Crawl Tiki listings into SQLite without duplicate products.

Usage:
    python3 scripts/crawl_tiki.py  # All 26 root categories
    python3 scripts/crawl_tiki.py --category-ids 1789,17166
    python3 scripts/crawl_tiki.py --category-ids 1520 --db data/tiki_crawl.db

Install dependencies with: uv pip install -r requirements.txt
Each successful page is committed independently;
rerunning safely revisits pages and updates existing products by Tiki product ID.
The database is never deleted. This script does not mark missing products inactive.
"""

import argparse
import hashlib
import json
import logging
import random
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests


LOG = logging.getLogger("tiki_crawler")
API_BASE = "https://tiki.vn"
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "tiki_crawl.db"

# Root categories from AnhTaizz/tiki_lakehouse/categories.txt.
CATEGORIES = {
    8322: "Nhà Sách Tiki",
    1883: "Nhà Cửa - Đời Sống",
    1789: "Điện Thoại - Máy Tính Bảng",
    2549: "Đồ Chơi - Mẹ & Bé",
    1815: "Thiết Bị Số - Phụ Kiện Số",
    1882: "Điện Gia Dụng",
    1520: "Làm Đẹp - Sức Khỏe",
    8594: "Ô Tô - Xe Máy - Xe Đạp",
    931: "Thời trang nữ",
    4384: "Bách Hóa Online",
    1975: "Thể Thao - Dã Ngoại",
    915: "Thời trang nam",
    17166: "Cross Border - Hàng Quốc Tế",
    1846: "Laptop - Máy Vi Tính - Linh kiện",
    1686: "Giày - Dép nam",
    4221: "Điện Tử - Điện Lạnh",
    1703: "Giày - Dép nữ",
    1801: "Máy Ảnh - Máy Quay Phim",
    27498: "Phụ kiện thời trang",
    44792: "NGON",
    8371: "Đồng hồ và Trang sức",
    6000: "Balo và Vali",
    11312: "Voucher - Dịch vụ",
    976: "Túi thời trang nữ",
    27616: "Túi thời trang nam",
    15078: "Chăm sóc nhà cửa",
}


class TikiClient:
    def __init__(self, delay_min=4.0, delay_max=8.0, retries=3):
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.retries = retries

    def get(self, endpoint, params):
        url = f"{API_BASE}{endpoint}?{urlencode(params)}"
        for attempt in range(self.retries):
            time.sleep(random.uniform(self.delay_min, self.delay_max))
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://tiki.vn/",
            }
            try:
                with requests.get(url, headers=headers, timeout=30) as response:
                    response.raise_for_status()
                    payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    raise ValueError("API response must contain a data array")
                return payload
            except (requests.RequestException, ValueError) as exc:
                if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (401, 403):
                    raise RuntimeError(f"Tiki denied access (HTTP {exc.response.status_code}); stopping") from exc
                if attempt + 1 == self.retries:
                    raise RuntimeError(f"Request failed after {self.retries} attempts: {url}") from exc
                LOG.warning("Request failed (%s); retry %s/%s", exc, attempt + 1, self.retries)
                time.sleep(min(60, 5 * 2 ** attempt))


def leaf_categories(client, root_id):
    payload = client.get("/api/v2/categories", {"include": "children", "parent_id": root_id})

    def walk(nodes):
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get("id"), int):
                raise ValueError("Invalid category response")
            if node.get("is_leaf") is True or not node.get("children"):
                yield node["id"]
            else:
                yield from walk(node["children"])

    leaves = list(dict.fromkeys(walk(payload["data"])))
    return leaves or [root_id]


# 17 fields from the reference SQLite schema, plus 7 listing API fields.
PRODUCT_FIELDS = {
    "id": "INTEGER PRIMARY KEY", "sku": "TEXT", "name": "TEXT",
    "url_key": "TEXT", "price": "INTEGER", "original_price": "INTEGER",
    "discount": "INTEGER", "discount_rate": "INTEGER", "brand_name": "TEXT",
    "rating_average": "REAL", "review_count": "INTEGER", "thumbnail_url": "TEXT",
    "category_id": "INTEGER", "quantity_sold": "INTEGER", "category_name": "TEXT",
    "crawl_date": "TEXT", "is_active": "INTEGER",
    "seller_id": "INTEGER", "seller_product_id": "INTEGER", "url_path": "TEXT",
    "inventory_status": "TEXT", "stock_item": "TEXT", "short_description": "TEXT",
    "type": "TEXT",
}


def open_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    existing = [row[1] for row in conn.execute("PRAGMA table_info(products)")]
    if existing and existing != list(PRODUCT_FIELDS):
        conn.close()
        raise ValueError("Incompatible products schema; migrate or reset this database before crawling")
    columns = ", ".join(f'"{name}" {kind}' for name, kind in PRODUCT_FIELDS.items())
    conn.execute(f"CREATE TABLE IF NOT EXISTS products ({columns})")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS product_checkpoints (
            product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
            content_hash TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_changed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_raw (
            product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
            raw_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_categories (
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            root_category_id INTEGER NOT NULL,
            leaf_category_id INTEGER NOT NULL,
            PRIMARY KEY (product_id, root_category_id, leaf_category_id)
        );
    """)
    return conn


def normalize_product(item, root_id, crawl_date):
    product = {name: item.get(name) for name in PRODUCT_FIELDS}
    product["category_id"] = root_id
    product["category_name"] = CATEGORIES.get(root_id)
    product["crawl_date"] = crawl_date
    # A listing is visible, but visibility does not prove inventory availability.
    active = item.get("is_active", item.get("is_visible"))
    product["is_active"] = None if active is None else int(bool(active))
    if product["original_price"] is None:
        product["original_price"] = item.get("list_price")
    sold = item.get("quantity_sold")
    product["quantity_sold"] = sold.get("value") if isinstance(sold, dict) else sold
    for name, value in product.items():
        if isinstance(value, (dict, list)):
            product[name] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return product


def save_page(conn, items, root_id, leaf_id):
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    crawl_date = datetime.now().astimezone().date().isoformat()
    names = list(PRODUCT_FIELDS)
    columns = ", ".join(f'"{name}"' for name in names)
    placeholders = ", ".join("?" for _ in names)
    updates = ", ".join(f'"{name}"=excluded."{name}"' for name in names if name != "id")
    with conn:
        for item in items:
            if not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0:
                raise ValueError("Product is missing a valid integer ID; page was rolled back")
            raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            # Compare source data, excluding crawl timestamps generated by us.
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            previous = conn.execute(
                "SELECT content_hash FROM product_checkpoints WHERE product_id=?", (item["id"],)
            ).fetchone()
            status = "new" if previous is None else "unchanged" if previous[0] == digest else "updated"
            counts[status] += 1
            if status != "unchanged":
                product = normalize_product(item, root_id, crawl_date)
                conn.execute(f"INSERT INTO products ({columns}) VALUES ({placeholders}) "
                             f"ON CONFLICT(id) DO UPDATE SET {updates}",
                             tuple(product[name] for name in names))
                conn.execute("""INSERT INTO product_raw VALUES (?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET raw_json=excluded.raw_json""",
                    (item["id"], raw))
            else:
                conn.execute("UPDATE products SET crawl_date=? WHERE id=?", (crawl_date, item["id"]))
            conn.execute("""INSERT INTO product_checkpoints VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    content_hash=excluded.content_hash,
                    last_seen_at=excluded.last_seen_at,
                    last_changed_at=CASE
                        WHEN product_checkpoints.content_hash != excluded.content_hash
                        THEN excluded.last_changed_at ELSE product_checkpoints.last_changed_at END
                """, (item["id"], digest, now, now, now))
            conn.execute("""INSERT INTO product_categories VALUES (?, ?, ?)
                            ON CONFLICT DO NOTHING""", (item["id"], root_id, leaf_id))
    return counts


def crawl_category(client, conn, root_id):
    totals = {"new": 0, "updated": 0, "unchanged": 0}
    for leaf_id in leaf_categories(client, root_id):
        page = 1
        fingerprints = set()
        while True:
            payload = client.get("/api/personalish/v1/blocks/listings", {
                "limit": 40, "category": leaf_id, "page": page,
            })
            items = payload["data"]
            if not items:
                break
            fingerprint = tuple(item.get("id") for item in items)
            if fingerprint in fingerprints:
                raise RuntimeError(f"Repeated page in category {leaf_id}; stopping to avoid an infinite crawl")
            fingerprints.add(fingerprint)
            counts = save_page(conn, items, root_id, leaf_id)
            for key, value in counts.items():
                totals[key] += value
            LOG.info("root=%s leaf=%s page=%s fetched=%s %s", root_id, leaf_id, page, len(items), counts)
            # Probe until an empty page, as in the reference crawler. Do not rely
            # solely on last_page, which may be capped by the listing endpoint.
            page += 1
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category-ids", help="Comma-separated Tiki root category IDs; defaults to all 26 categories")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite output (separate from the reference simulator DB)")
    parser.add_argument("--delay-min", type=float, default=4.0)
    parser.add_argument("--delay-max", type=float, default=8.0)
    args = parser.parse_args()
    try:
        category_ids = (
            list(CATEGORIES) if args.category_ids is None else
            list(dict.fromkeys(int(value.strip()) for value in args.category_ids.split(",")))
        )
        if any(value <= 0 for value in category_ids):
            raise ValueError
    except ValueError:
        parser.error("--category-ids must contain positive integers separated by commas")
    if not 0 <= args.delay_min <= args.delay_max:
        parser.error("Require 0 <= --delay-min <= --delay-max")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = open_database(args.db)
    try:
        client = TikiClient(args.delay_min, args.delay_max)
        LOG.info("Selected %s root categories", len(category_ids))
        for root_id in category_ids:
            LOG.info("Starting category %s: %s", root_id, CATEGORIES.get(root_id, "Custom category"))
            LOG.info("Category %s completed: %s", root_id, crawl_category(client, conn, root_id))
        LOG.info("Done. Database: %s; unique products: %s", args.db.resolve(),
                 conn.execute("SELECT COUNT(*) FROM products").fetchone()[0])
        return 0
    except (RuntimeError, ValueError, sqlite3.Error, KeyboardInterrupt) as exc:
        LOG.error("Crawl stopped: %s. Committed pages are retained; rerun safely to retry.", exc)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
