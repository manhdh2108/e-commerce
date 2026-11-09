"""Build docs/mock-design/examples/scenarios/dw-scd-2026.json from dw-lite-2026.json.

Purpose (DW plan step 1.0): from 2026-01-25 on, generate dimension changes for SCD 1/2/3
and multi-channel ad spend. Engine code is unchanged; only the scenario config differs.
Deterministic: no randomness here; the engine's seeded RNG picks targets.

    python scripts/mock_runner/make_dw_scd_config.py
"""
import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCEN = ROOT / "docs/mock-design/examples/scenarios"
SWITCH = dt.date(2026, 1, 25)  # first day simulated with this config
END = dt.date(2026, 12, 31)

src = json.loads((SCEN / "dw-lite-2026.json").read_text(encoding="utf-8"))
cfg = src["config"]


def days(step, offset=0):
    """Dates from SWITCH..END every `step` days (as ISO strings)."""
    out, d = [], SWITCH + dt.timedelta(days=offset)
    while d <= END:
        out.append(d.isoformat())
        d += dt.timedelta(days=step)
    return out


def enable(code, pool, count=0, special=None, params=None, variants=None, mode=None):
    c = cfg[code]
    c["enabled"] = True
    c["mode"] = "count"
    c["actor_pool"] = pool
    c["count"] = count
    c["special"] = special or {}
    c["params"] = params or {}
    if variants:
        c["variants"] = variants
    if mode:
        c["variant_mode"] = mode


def v(name, weight, **params):
    return {"name": name, "weight": weight, "params": params}


PROVINCES = [v("Chuyển về TP. Hồ Chí Minh", 4, province="TP. Hồ Chí Minh"),
             v("Chuyển về Hà Nội", 4, province="Hà Nội"),
             v("Chuyển về Đà Nẵng", 2, province="Đà Nẵng")]

# --- SCD2 khách: hạng thành viên (mini-dimension / SCD2) và tỉnh cư trú -------------
enable("SYS-03", "orders-team-8", count=25, variants=[
    v("Hạng Member", 2, new_tier="Member"), v("Hạng Silver", 5, new_tier="Silver"),
    v("Hạng Gold", 3, new_tier="Gold"), v("Hạng Platinum", 1, new_tier="Platinum")])
enable("CUS-02", "customers", count=3, variants=PROVINCES)

# --- SCD2/SCD3 seller: hạng; SCD2 tỉnh; trạng thái (khóa shop) -------------------------
enable("MGR-01", "catalog-team-3", count=1, params={"reason": "Xét hạng định kỳ"}, variants=[
    v("Lên/giữ Preferred", 5, tier="Preferred"), v("Về Normal", 3, tier="Normal"),
    v("Lên Mall", 2, tier="Mall")])
enable("SEL-03", "sellers", special={d: 1 for d in days(4)}, variants=PROVINCES)
enable("MGR-02", "catalog-team-3",
       special={d: 1 for d in ["2026-01-27", "2026-03-16", "2026-06-15", "2026-09-15", "2026-12-15"]},
       params={"reason": "Vi phạm chính sách mô phỏng"})

# --- SCD1 seller: đổi tên shop (tên tự sinh), giữ SEL-02 (liên hệ) đang có ------------
enable("SEL-01", "sellers", special={d: 1 for d in days(10, 1)})

# --- Quảng cáo đa kênh: 3 chiến dịch (WEB/APP/LIVESTREAM) mỗi đợt, ngân sách đủ 31 ngày --
mkt = cfg["MKT-01"]
mkt["params"] = {**mkt.get("params", {}), "amount": 12000000, "days": 31}
mkt["variant_mode"] = "cycle"
mkt["variants"] = [
    v("Web · Khám phá sản phẩm mới", 1, campaign_channel="WEB", value="Khám phá sản phẩm mới",
      campaign_type="Brand Awareness"),
    v("App · Ưu đãi trên ứng dụng", 1, campaign_channel="APP", value="Ưu đãi trên ứng dụng",
      campaign_type="Retargeting"),
    v("Livestream · Săn deal trực tiếp", 1, campaign_channel="LIVESTREAM",
      value="Săn deal trực tiếp", campaign_type="Livestream Show"),
]
mkt["special"] = {d: 3 for d, n in mkt.get("special", {}).items() if n and d >= SWITCH.isoformat()}
cfg["ADS-01"]["count"] = 4  # mỗi chiến dịch đang chạy tối đa 1 báo cáo/ngày

src["name"] = "DW 2026 · SCD + quảng cáo đa kênh (áp dụng từ 25/01)"
out = SCEN / "dw-scd-2026.json"
out.write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")
print("written", out)
