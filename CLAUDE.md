# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A university data-warehouse project (PTIT) for a multi-seller e-commerce marketplace. At present it holds **one crawler script and a set of Vietnamese design docs**. The OLTP generator and the DW/ETL layer are specified in the docs but **not yet implemented**. There is no README, test suite, linter, or build system.

The intended pipeline:

```
Tiki public API ──crawl_tiki.py──▶ data/tiki_crawl.db (SQLite, real data)
                                        │
                                        ▼  (generator, not written yet; spec: DATA_GENERATION_RULES.md)
                         OLTP database, simulated day by day (27 business tables)
                                        │
                                        ▼  (ETL, out of scope of the generator)
                         Data warehouse: Fact_* / Dim_* (see OLTP_SCHEMA.md §13)
```

Only `products` is real data. Every other OLTP table (orders, customers, payments, inventory, ads, clickstream, payouts...) is simulated.

## Commands

```bash
pip install -r requirements.txt            # only dependency: requests (the script docstring suggests `uv pip install -r requirements.txt`)

python scripts/crawl_tiki.py                                  # all 26 root categories
python scripts/crawl_tiki.py --category-ids 1789,17166        # selected root categories
python scripts/crawl_tiki.py --category-ids 1520 --db data/tiki_crawl.db
python scripts/crawl_tiki.py --delay-min 4 --delay-max 8      # request jitter (seconds), defaults shown
```

- Default output is `data/tiki_crawl.db` (git-ignored via `*.db`, `*.db-*`; `data/` is created on demand).
- A full crawl is slow by design (4–8 s random delay per request, every leaf category, paged until an empty page). Use `--category-ids` for experiments.
- There are no tests or lint config. Verify crawler changes by running against one small category and inspecting the SQLite file.

## Crawler architecture (`scripts/crawl_tiki.py`)

Single file, three layers:

1. `TikiClient.get` — sleeps a random delay, retries 3x with exponential backoff, **aborts immediately on HTTP 401/403**, and requires the JSON to have a `data` list.
2. `crawl_category` — for a root category, `leaf_categories()` walks `/api/v2/categories` to find leaves, then pages `/api/personalish/v1/blocks/listings` (limit 40) per leaf **until an empty page** (not `last_page`, which the endpoint caps). A repeated page fingerprint raises to prevent infinite loops.
3. `save_page` — one transaction per page across four tables. Each item is JSON-serialized and SHA-256 hashed:
   - new/changed hash → upsert `products` (24 columns, `PRODUCT_FIELDS`) + `product_raw`
   - unchanged hash → only refresh `products.crawl_date`
   - always upsert `product_checkpoints` and insert the (product, root, leaf) row in `product_categories`

Things that are easy to get wrong:

- `products.category_id` / `category_name` hold the **root** category (the one being crawled), not the leaf. Leaves live only in `product_categories`, and one product can have several root/leaf pairs.
- `open_database` raises if an existing `products` table's columns differ from `PRODUCT_FIELDS` (exact order). Changing `PRODUCT_FIELDS` means migrating or recreating the DB; the crawler never deletes the DB or marks missing products inactive.
- `is_active` is `is_active`/`is_visible` from the API or NULL — it is visibility, not stock. `quantity_sold` is unwrapped from `{"value": ...}`; `original_price` falls back to `list_price`; dict/list values are stored as JSON text.
- `CATEGORIES` (26 root IDs) is the only hardcoded ID set; the generator spec relies on it (fulfillment classes use 11312 = digital, 17166 = cross-border).
- Each run restarts from page 1 (no page-resume); rerunning is idempotent by Tiki product ID.

## Docs (all in Vietnamese; `docs/`)

Read these before designing or writing anything downstream; they are the source of truth.

- `SCHEMA.md` — the 24-column crawler SQLite schema (17 reference columns from `AnhTaizz/tiki_lakehouse` + 7 extra API fields) and its 3 helper tables.
- `OLTP_SCHEMA.md` — full OLTP schema: 27 business tables in 6 source systems (catalog/sellers, orders, warehouse/logistics, marketing, clickstream, finance) + 3 crawler tables; §10 lists deliberately inconsistent cross-system keys (e.g. warehouse uses `sku`/`order_code`, marketing uses `WEB`/`MOBILE_APP`/`LIVE`) that ETL must reconcile; §13 maps OLTP tables to Fact/Dim tables. Rows marked **[mới]** were added later.
- `OLTP_ERD.md` — Mermaid ERDs (overview + column-level).
- `DATA_GENERATION_RULES.md` — ~1300-line spec for the simulator. Rules are coded `R-<group>-<n>`, scenarios `S-<group>-<n>`, invariants `V-<n>`; priority on conflict is **data integrity > business logic > statistical distribution**. Key design constraints:
  - Reads the crawl DB read-only; input contract and filtering are §1; simulation parameters (`dev` vs `full` profiles, single seeded RNG) are §2.
  - Event-driven, one global clock, day-by-day loop (§4); resumable with `--until <date>` pause points so ETL can read mid-simulation.
  - Reproducibility: sort entity sets by ID before any seeded sampling (R-ID-06); never hardcode product/seller/category IDs (R-ID-05).
  - OLTP stores **current state only**, never DELETEs (R-SIM-06), and sets `updated_at` on every UPDATE (R-SIM-05). SCD history, bridges, code mapping and dirty-data cleaning are ETL's job — the generator must not bend business logic to create DW test cases.
  - Money is integer VND; timestamps are UTC+7 without timezone; Vietnam's 34-province admin model (`new_34`) is the default.
  - §17 injects source-system errors; §18 lists post-generation invariants; §19 lists schema changes the rules required (already applied to the schema docs).
- `FACT_REVIEW.md` — review of the three proposed facts (`Fact_Order_Item`, `Fact_Inventory_Snapshot`, `Fact_Ad_Spend`) against the proposal PDF `DeXuat_KhoDuLieu_TMDT.pdf` (not in the repo): e.g. `Date_Key` should be the Completed date, snapshot needs cost history, promotion bridge needed.

When changing the schema, keep `OLTP_SCHEMA.md`, `OLTP_ERD.md`, and the §19 change table in `DATA_GENERATION_RULES.md` consistent with each other.
