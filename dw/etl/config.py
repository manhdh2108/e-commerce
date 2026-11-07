"""Cấu hình ETL. Có thể ghi đè bằng biến môi trường (DW_SOURCE_URL, DW_TARGET_URL, MOCK_API, TIKI_DB)."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Nguồn OLTP: role CHỈ ĐỌC (bước 02). Đích: kho dwh bằng dw_etl.
SOURCE_URL = os.getenv("DW_SOURCE_URL", "postgresql://dw_reader:dw_reader_local@127.0.0.1:55432/mock_oltp")
TARGET_URL = os.getenv("DW_TARGET_URL", "postgresql://dw_etl:dw_etl_local@127.0.0.1:55432/dwh")
# Watermark: ngày mô phỏng cuối cùng đã hoàn tất (Mock Studio)
MOCK_API = os.getenv("MOCK_API", "http://127.0.0.1:8765")
# Crawler Tiki: bản sao journal_mode=DELETE (WSL không đọc ổn định file WAL gốc)
TIKI_DB = pathlib.Path(os.getenv("TIKI_DB", ROOT / "data/tiki_crawl_share.db"))
SOURCE_SYSTEM = "mock_oltp"
# Mốc trước ngày đầu tiên của dữ liệu (watermark_from của batch đầu tiên, không gồm)
INITIAL_WATERMARK = "2025-12-31"
