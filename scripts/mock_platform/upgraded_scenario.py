"""Version 2 demonstration: connected journeys, mixtures and delayed consequences."""

import json
from pathlib import Path

from .scenario import RealisticScenario
from .service import PlatformService


class UpgradedScenario(RealisticScenario):
    def build(self):
        document = super().build()
        document.update(
            format_version=2,
            name=f"Vận hành liên kết {self.year} · profile & nghiệp vụ qua ngày",
        )
        cfg = document["config"]

        def profiles(code, rows):
            cfg[code]["variants"] = [
                {"name": name, "weight": weight, "params": params}
                for name, weight, params in rows
            ]

        def action(code, count=0, params=None, auto=False, delay=0):
            cfg[code] = {
                "enabled": True,
                "count": count,
                "mode": "all" if auto else "count",
                "special": {},
                "params": params or {},
            }
            if delay:
                cfg[code]["delay_days"] = delay

        profiles(
            "GST-01",
            [
                ("Miền Nam", 5, {"province": "TP. Hồ Chí Minh"}),
                ("Miền Bắc", 3, {"province": "Hà Nội"}),
                ("Miền Trung", 2, {"province": "Đà Nẵng"}),
            ],
        )
        for prefix in ["GST", "CUS"]:
            profiles(
                prefix + "-WEB-01",
                [
                    (
                        "Điện thoại tự nhiên",
                        40,
                        {"channel": "Web", "device": "Mobile", "traffic": "Organic"},
                    ),
                    (
                        "Máy tính tìm kiếm",
                        20,
                        {"channel": "Web", "device": "Desktop", "traffic": "Organic"},
                    ),
                    (
                        "Ứng dụng trực tiếp",
                        25,
                        {"channel": "App", "device": "Mobile", "traffic": "Direct"},
                    ),
                    (
                        "Điện thoại mạng xã hội",
                        10,
                        {
                            "channel": "Web",
                            "device": "Mobile",
                            "traffic": "Social",
                            "campaign": "auto",
                        },
                    ),
                    (
                        "Máy tính từ email",
                        5,
                        {
                            "channel": "Web",
                            "device": "Desktop",
                            "traffic": "Email",
                            "campaign": "auto",
                        },
                    ),
                ],
            )
            profiles(
                prefix + "-WEB-02",
                [
                    ("Tìm sách", 3, {"value": "sách kỹ năng"}),
                    ("Tìm văn phòng phẩm", 2, {"value": "văn phòng phẩm"}),
                    ("Tìm quà", 1, {"value": "quà tặng"}),
                ],
            )
            profiles(
                prefix + "-WEB-04",
                [
                    ("Một sản phẩm", 8, {"quantity": 1}),
                    ("Hai sản phẩm", 2, {"quantity": 2}),
                ],
            )
            order = cfg["GST-02" if prefix == "GST" else "CUS-05"]
            order["params"] = {
                "checkout_mode": "linked",
                "voucher_mode": "none" if prefix == "GST" else "auto",
                "shipping_fee": 20000,
            }
            order["variants"] = [
                {"name": name, "weight": weight, "params": {"method": method}}
                for name, weight, method in [
                    ("Nhận hàng trả tiền", 45, "COD"),
                    ("Ví MoMo", 25, "Momo"),
                    ("Ví ZaloPay", 15, "ZaloPay"),
                    ("Thẻ tín dụng", 10, "Credit Card"),
                    ("Chuyển khoản", 5, "Bank Transfer"),
                ]
            ]
            # Same number of checkout intents as requests; cart availability still governs actual output.
            rows = self.schedule()
            key = "guest_orders" if prefix == "GST" else "customer_orders"
            action(prefix + "-WEB-06", 5 if prefix == "GST" else 15)
            cfg[prefix + "-WEB-06"]["special"] = {
                r["day"]: r[key]
                for r in rows
                if r[key] != cfg[prefix + "-WEB-06"]["count"]
            }
            action(prefix + "-WEB-05", 1)
        cfg["SEL-05"]["enabled"] = (
            False  # do not rewrite real product text just for variety
        )
        cfg["CUS-03"]["enabled"] = (
            False  # address creation/reuse belongs to checkout unless explicitly requested
        )
        cfg["DSP-01"]["params"] = {"warehouse": 0, "carrier": 0, "amount": 30000}
        cfg["DSP-01"]["delay_days"] = 1
        cfg["CAR-03"]["params"] = {"success_rate": 95}
        cfg["CAR-03"]["delay_days"] = 1
        action("CAR-06", auto=True)
        action(
            "CAR-05", auto=True
        )  # retry is later that day; unretryable failures return to origin
        # Return-to-origin runs before retry in code priority. Prefer retry first, automatic RTO only at limit.
        cfg["CAR-05"]["params"] = {"return_policy": "attempts_exhausted"}
        cfg["CUS-09"]["delay_days"] = 1
        profiles(
            "CUS-09",
            [
                (
                    "Hài lòng",
                    55,
                    {"rating": 5, "value": "Sản phẩm phù hợp, đóng gói cẩn thận."},
                ),
                (
                    "Khá hài lòng",
                    30,
                    {"rating": 4, "value": "Hàng đúng mô tả, giao nhận ổn."},
                ),
                (
                    "Trung bình",
                    10,
                    {
                        "rating": 3,
                        "value": "Sản phẩm dùng được, trải nghiệm còn điểm cần cải thiện.",
                    },
                ),
                (
                    "Chưa hài lòng",
                    5,
                    {"rating": 2, "value": "Trải nghiệm chưa đáp ứng kỳ vọng."},
                ),
            ],
        )
        action(
            "CUS-08",
            count=1,
            params={"quantity": 1, "reason": "Sản phẩm không phù hợp nhu cầu"},
        )
        action("SUP-01", auto=True)
        action("WH-04", auto=True, delay=2)
        action("PAY-02", auto=True, delay=1)
        action(
            "FIN-POL-01",
            auto=True,
            params={
                "scope": "all_leaf",
                "tier": "Normal",
                "rate": 5,
                "start": f"{self.year}-01-01",
                "end": f"{self.year}-12-31",
            },
        )
        action("FIN-REC-01", auto=True)
        action("FIN-REC-02", auto=True)
        action("FIN-PAY-01", auto=True)
        profiles(
            "MKT-01",
            [
                (
                    "Chiến dịch sách",
                    6,
                    {
                        "value": "Khám phá sách hay · mô phỏng",
                        "campaign_type": "Brand Awareness",
                        "campaign_channel": "WEB",
                    },
                ),
                (
                    "Khuyến khích mua",
                    4,
                    {
                        "value": "Ưu đãi mua sắm · mô phỏng",
                        "campaign_type": "Conversion",
                        "campaign_channel": "APP",
                    },
                ),
            ],
        )
        profiles(
            "ADS-01",
            [
                (
                    "Lượt tiếp cận rộng",
                    6,
                    {"amount": 50000, "quantity": 60, "impressions": 5000},
                ),
                (
                    "Nhóm quan tâm cao",
                    4,
                    {"amount": 80000, "quantity": 100, "impressions": 4000},
                ),
            ],
        )
        for code, name in [
            ("MKT-03", "Ưu đãi sàn mô phỏng"),
            ("MKT-04", "Hỗ trợ phí giao mô phỏng"),
            ("SHOP-MKT-01", "Ưu đãi riêng cửa hàng mô phỏng"),
        ]:
            cfg[code]["params"]["value"] = name
        PlatformService().validate_config(cfg)
        return document


def main():
    target = (
        Path(__file__).resolve().parents[2]
        / "docs/mock-design/examples/scenarios/upgraded-linked-2026.json"
    )
    target.write_text(
        json.dumps(UpgradedScenario().build(), ensure_ascii=False, indent=2) + "\n"
    )
    print(target)


if __name__ == "__main__":
    main()
