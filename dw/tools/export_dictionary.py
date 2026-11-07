"""Xuất từ điển dữ liệu (audit.data_dictionary) ra Markdown — PLAN 4.7 / Milestone 3.3.

    python dw/tools/export_dictionary.py
Đọc qua `docker exec … psql` nên không cần cài driver Postgres trên Windows.
"""
import csv, io, pathlib, subprocess, sys
from collections import OrderedDict

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/data-model/warehouse/M3_TU_DIEN_DU_LIEU.md"
CONTAINER = "scripts-mock-postgres-1"
SQL = r"""copy (select table_name, coalesce(table_description,''), ordinal_position, column_name, data_type,
  case when nullable then 'có' else 'không' end, coalesce(description,''), coalesce(source,''), coalesce(rule,''),
  coalesce(additivity,''), coalesce(scd_type,'')
  from audit.data_dictionary order by case when table_name like 'fact%' then 0 when table_name like 'bridge%' then 2 else 1 end,
  table_name, ordinal_position) to stdout with csv"""

ADD = {"A": "Additive", "SA": "Semi-additive", "NA": "Non-additive", "KEY": "Khóa", "ATTR": "Thuộc tính", "TECH": "Kỹ thuật"}

raw = subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", "dw_etl", "-d", "dwh", "-c", SQL],
                     capture_output=True, check=True).stdout.decode("utf-8")
tables = OrderedDict()
for r in csv.reader(io.StringIO(raw)):
    tables.setdefault(r[0], {"desc": r[1], "cols": []})["cols"].append(r[2:])

esc = lambda s: s.replace("|", "\\|").replace("\n", " ")
lines = ["# Milestone 3.3 — Từ điển dữ liệu (schema `dw`)", "",
         "File này được **sinh tự động** từ `audit.data_dictionary` (catalog Postgres + `COMMENT ON` + `audit.column_lineage`) "
         "bằng `python dw/tools/export_dictionary.py`. Đừng sửa tay — sửa `dw/sql/50_audit/502_dictionary_metadata.sql` rồi chạy lại.", "",
         "Cột *Cộng*: Additive / Semi-additive (không cộng theo thời gian) / Non-additive (tính lại từ tử và mẫu). "
         "Cột *SCD*: 1 ghi đè, 2 phiên bản lịch sử, 3 giữ giá trị trước, mini = mini-dimension.", "",
         f"Tổng: **{len(tables)} bảng**, **{sum(len(t['cols']) for t in tables.values())} cột**.", "", "## Mục lục", ""]
lines += [f"- [`{t}`](#{t.replace('_', '_')}) — {esc(v['desc'])[:110]}" for t, v in tables.items()]
for t, v in tables.items():
    lines += ["", f"## {t}", "", esc(v["desc"]), "",
              "| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |",
              "|---|---|---|---|---|---|---|---|---|"]
    for pos, col, typ, nul, d, src, rule, add, scd in v["cols"]:
        lines.append(f"| {pos} | `{col}` | {typ} | {nul} | {esc(d)} | {esc(src)} | {esc(rule)} | {ADD.get(add, add)} | {scd} |")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written", OUT, len(tables), "tables")
