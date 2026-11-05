"""Build a reproducible calendar using only currently supported action fields.

These are explicit demo assumptions, not measured Tiki traffic or industry ratios.
"""

import argparse
import calendar
import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from .service import ACTIONS, PlatformService


class RealisticScenario:
    def __init__(self, year=2026, category_id=9423):
        self.year, self.category_id = year, category_id
        self.sale_days = {date(year, m, m) for m in [8, 10, 11, 12]}

    def schedule(self):
        day = date(self.year, 1, 1)
        rows = []
        while day.year == self.year:
            variation = (
                int(hashlib.sha256(f"volume-v1:{day}".encode()).hexdigest()[:8], 16) % 7
                - 3
            )
            base = [16, 18, 19, 20, 22, 27, 24][day.weekday()] + variation
            kind, factor = "Ngày thường", 1.0
            if day.weekday() >= 5:
                kind = "Cuối tuần"
            if 25 <= day.day <= 28:
                kind, factor = "Giả định kỳ lương", 1.15
            if any(
                day == sale - timedelta(days=n)
                for sale in self.sale_days
                for n in [1, 2]
            ):
                kind, factor = "Trước sale", 1.5
            if any(day == sale + timedelta(days=1) for sale in self.sale_days):
                kind, factor = "Sau sale", 1.4
            if day in self.sale_days:
                kind, factor = "Sale theo kịch bản", 4.0
            orders = max(4, round(base * factor))
            guest = max(1, round(orders * 0.25))
            sessions = orders * 15
            guest_sessions = round(sessions * 0.6)
            rows.append(
                {
                    "day": day.isoformat(),
                    "kind": kind,
                    "orders": orders,
                    "guest_orders": guest,
                    "customer_orders": orders - guest,
                    "guest_sessions": guest_sessions,
                    "customer_sessions": sessions - guest_sessions,
                    "register": max(1, round(sessions * 0.015)),
                    "reviews": max(1, orders // 6),
                }
            )
            day += timedelta(days=1)
        return rows

    def build(self):
        config = {
            code: {
                "enabled": False,
                "count": 0,
                "mode": "count",
                "special": {},
                "params": {},
            }
            for code in ACTIONS
        }
        rows = self.schedule()

        def action(code, count=0, params=None, special=None, automatic=False):
            config[code] = {
                "enabled": True,
                "count": count,
                "mode": "all" if automatic else "count",
                "special": special or {},
                "params": params or {},
            }

        def schedule(code, normal, selector, params=None):
            action(
                code,
                normal,
                params,
                {r["day"]: selector(r) for r in rows if selector(r) != normal},
            )

        schedule("GST-01", 5, lambda r: r["register"], {"province": "TP. Hồ Chí Minh"})
        schedule(
            "GST-02",
            5,
            lambda r: r["guest_orders"],
            {"quantity": 1, "method": "COD", "channel": "Web"},
        )
        schedule(
            "CUS-05",
            15,
            lambda r: r["customer_orders"],
            {"quantity": 1, "method": "Momo", "channel": "App"},
        )
        action("PAY-01", params={"success_rate": 94}, automatic=True)
        action("ORD-01", automatic=True)
        action("SYS-01", params={"days": 2}, automatic=True)
        schedule(
            "CUS-09",
            3,
            lambda r: r["reviews"],
            {"rating": 4, "value": "Đánh giá thử nghiệm sau giao hàng"},
        )
        action(
            "CUS-03",
            special={
                r["day"]: 1 for r in rows if date.fromisoformat(r["day"]).weekday() == 2
            },
            params={"province": "TP. Hồ Chí Minh"},
        )
        action(
            "SEL-05",
            special={
                r["day"]: 1 for r in rows if date.fromisoformat(r["day"]).weekday() == 0
            },
            params={
                "value": "Thông tin sản phẩm được người bán kiểm tra lại (mô phỏng)."
            },
        )
        firsts = {date(self.year, month, 1).isoformat(): 1 for month in range(1, 13)}
        action("SEL-02", special=firsts)
        action(
            "WH-01",
            1,
            {"warehouse": 1, "quantity": 20},
            {r["day"]: 3 for r in rows if r["kind"] == "Trước sale"},
        )
        action("DSP-01", params={"warehouse": 1, "amount": 30000}, automatic=True)
        for code in ["CAR-01", "CAR-02", "CAR-04"]:
            action(code, automatic=True)
        action("CAR-03", params={"success_rate": 100}, automatic=True)
        action("AUT-WH-04", 1)
        action(
            "MKT-01",
            params={
                "value": "Nhận diện shop sách · mô phỏng",
                "amount": 3000000,
                "days": 31,
            },
            special=firsts,
        )
        promotion_days = {**firsts, **{d.isoformat(): 1 for d in self.sale_days}}
        for code, amount, minimum in [
            ("MKT-03", 20000, 200000),
            ("MKT-04", 15000, 150000),
            ("SHOP-MKT-01", 10000, 100000),
        ]:
            action(
                code,
                params={
                    "amount": amount,
                    "min_order": minimum,
                    "limit": 1000,
                    "days": 7,
                },
                special=promotion_days,
            )
        action("ADS-01", 1, {"amount": 50000, "quantity": 60})
        action("AUT-MKT-03", 1)
        for prefix, key, channel, traffic, normal in [
            ("GST", "guest_sessions", "Web", "Organic", 180),
            ("CUS", "customer_sessions", "App", "Direct", 120),
        ]:
            schedule(
                prefix + "-WEB-01",
                normal,
                lambda r, k=key: r[k],
                {"channel": channel, "device": "Mobile", "traffic": traffic},
            )
            schedule(prefix + "-WEB-02", normal // 2, lambda r, k=key: r[k] // 2)
            schedule(prefix + "-WEB-03", normal * 2, lambda r, k=key: r[k] * 2)
            share = 0.4 if prefix == "GST" else 0.6
            schedule(
                prefix + "-WEB-04",
                round(20 * 3 * share),
                lambda r, x=share: round(r["orders"] * 3 * x),
                {"quantity": 1},
            )
        action("AUT-WEB-01", automatic=True)
        action("AUT-WEB-02", automatic=True)
        action(
            "FIN-POL-01",
            params={
                "category": self.category_id,
                "tier": "Normal",
                "rate": 5,
                "start": date(self.year, 1, 1).isoformat(),
                "end": date(self.year, 12, 31).isoformat(),
            },
            special={date(self.year, 1, 1).isoformat(): 1},
        )
        PlatformService().validate_config(config)
        return {
            "format": "mock-studio-config",
            "format_version": 1,
            "name": f"Vận hành có lịch biến thiên {self.year} · trong phạm vi engine hiện tại",
            "config": config,
        }

    def monthly_stats(self):
        config = self.build()["config"]
        output = []
        for month in range(1, 13):
            days = [
                r
                for r in self.schedule()
                if date.fromisoformat(r["day"]).month == month
            ]
            explicit = sum(
                cfg["special"].get(r["day"], cfg["count"])
                for cfg in config.values()
                if cfg["enabled"] and cfg["mode"] == "count"
                for r in days
            )
            output.append(
                {
                    "month": f"{self.year}-{month:02}",
                    "days": calendar.monthrange(self.year, month)[1],
                    "requested_orders": sum(r["orders"] for r in days),
                    "count_actions": explicit,
                }
            )
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--category-id", type=int, default=9423)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/mock-design/examples/scenarios/realistic-current-engine-2026.json"),
    )
    args = parser.parse_args()
    scenario = RealisticScenario(args.year, args.category_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(scenario.build(), ensure_ascii=False, indent=2) + "\n"
    )
    with args.output.with_suffix(".csv").open("w", newline="") as handle:
        rows = scenario.schedule()
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(scenario.monthly_stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
