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


def open_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price INTEGER,
            original_price INTEGER,
            discount_rate INTEGER,
            quantity_sold INTEGER,
            raw_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_changed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_categories (
            product_id INTEGER NOT NULL REFERENCES products(id),
            root_category_id INTEGER NOT NULL,
            leaf_category_id INTEGER NOT NULL,
            PRIMARY KEY (product_id, root_category_id, leaf_category_id)
        );
    """)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def save_page(conn, items, root_id, leaf_id):
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with conn:
        for item in items:
            if not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0:
                raise ValueError("Product is missing a valid integer ID; page was rolled back")
            raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            previous = conn.execute("SELECT content_hash FROM products WHERE id=?", (item["id"],)).fetchone()
            status = "new" if previous is None else "unchanged" if previous[0] == digest else "updated"
            counts[status] += 1
            sold = item.get("quantity_sold")
            if isinstance(sold, dict):
                sold = sold.get("value")
            if status == "unchanged":
                conn.execute("UPDATE products SET last_seen_at=? WHERE id=?", (now, item["id"]))
            else:
                conn.execute("""
                    INSERT INTO products (
                        id, name, price, original_price, discount_rate, quantity_sold,
                        raw_json, content_hash, first_seen_at, last_seen_at, last_changed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, price=excluded.price,
                        original_price=excluded.original_price,
                        discount_rate=excluded.discount_rate,
                        quantity_sold=excluded.quantity_sold,
                        raw_json=excluded.raw_json, content_hash=excluded.content_hash,
                        last_seen_at=excluded.last_seen_at,
                        last_changed_at=excluded.last_changed_at
                """, (item["id"], item.get("name"), item.get("price"),
                      item.get("original_price", item.get("list_price")),
                      item.get("discount_rate"), sold, raw, digest, now, now, now))
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
