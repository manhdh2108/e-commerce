# Tiki crawler SQLite schema

`products` has 24 columns. The reference repository's SQLite schema has
17 columns, not 24. This crawler keeps those 17 and adds 7 API listing fields.

Reference fields: `id`, `sku`, `name`, `url_key`, `price`, `original_price`,
`discount`, `discount_rate`, `brand_name`, `rating_average`, `review_count`,
`thumbnail_url`, `category_id`, `quantity_sold`, `category_name`, `crawl_date`,
`is_active`.

Additional API fields: `seller_id`, `seller_product_id`, `url_path`,
`inventory_status`, `stock_item`, `short_description`, `type`.

Source: https://github.com/AnhTaizz/tiki_lakehouse/blob/main/simulators/init_sqlite.py

Missing API values remain NULL. `stock_item` is JSON text. `quantity_sold`
extracts the nested `value`. `original_price` falls back to `list_price`.
Category ID/name come from the selected root category; `crawl_date` is the
local observation date. `is_active` uses `is_active` or `is_visible` if
provided, otherwise NULL. It is not a stock quantity or an inferred deletion.

Separate tables:

- `product_checkpoints`: product ID, source content hash, first/last seen and
  last changed timestamps (UTC). This is deduplication state, not a page-resume
  checkpoint. Each invocation starts crawling from page 1.
- `product_raw`: full, latest API JSON for each product.
- `product_categories`: unique product/root/leaf category memberships observed.

Product ID is unique. Source JSON is hashed before generated crawl metadata is
added. Changed products are upserted; unchanged products only refresh observation
metadata. All page writes across these tables commit in one transaction.
There is no price-history table; only the latest product state is retained.

The November 4, 2026 reset was explicitly requested by the user. Normal crawler
runs preserve the database and never delete existing products.
