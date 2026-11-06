"""Configurable synthetic identities shared by bootstrap and daily commands."""

import copy
import hashlib
import random

from ..config.configuration import DEFAULTS

DEFAULT_PROFILE = DEFAULTS["entity_profile"]


class EntityProfile:
    @staticmethod
    def validate(payload):
        from ..config.configuration import RuntimeConfiguration

        if (
            not isinstance(payload, dict)
            or not set(DEFAULT_PROFILE) <= set(payload)
            or set(payload) - (set(DEFAULT_PROFILE) | RuntimeConfiguration.EXTRAS)
        ):
            raise ValueError(
                "Hồ sơ cần surnames, given_names, locations, phone_prefixes, warehouses và carriers."
            )
        for key in ["surnames", "given_names", "phone_prefixes"]:
            rows = payload[key]
            if (
                not isinstance(rows, list)
                or not 1 <= len(rows) <= 1000
                or any(
                    not isinstance(x, str) or not x.strip() or len(x) > 100
                    for x in rows
                )
            ):
                raise ValueError(
                    f"{key}: cần danh sách văn bản không rỗng, tối đa 1.000 dòng."
                )
        if any(
            len(x) != 3 or not x.isdigit() or not x.startswith("0")
            for x in payload["phone_prefixes"]
        ):
            raise ValueError("Đầu số điện thoại mô phỏng gồm 3 chữ số, bắt đầu bằng 0.")
        for key, fields, identity in [
            ("locations", {"province", "city", "ward", "district", "street"}, None),
            (
                "warehouses",
                {"warehouse_code", "warehouse_name", "province", "city", "address"},
                "warehouse_code",
            ),
            ("carriers", {"carrier_code", "carrier_name"}, "carrier_code"),
        ]:
            rows = payload[key]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
                raise ValueError(f"{key}: cần từ 1 đến 100 dòng.")
            for row in rows:
                if not isinstance(row, dict) or set(row) != fields:
                    raise ValueError(f"{key}: sai danh sách trường.")
                for k, value in row.items():
                    if value is None and k == "district":
                        continue
                    if (
                        not isinstance(value, str)
                        or not value.strip()
                        or len(value) > 200
                    ):
                        raise ValueError(f"{key}.{k}: cần văn bản từ 1 đến 200 ký tự.")
            if identity and len({r[identity] for r in rows}) != len(rows):
                raise ValueError(f"{key}: mã bị trùng.")
        RuntimeConfiguration.validate(payload)
        return copy.deepcopy(payload)


class EntityGenerator:
    def __init__(self, profile=None, seed=42):
        self.p = profile or DEFAULT_PROFILE
        self.seed = seed

    def rng(self, identity):
        return random.Random(
            hashlib.sha256(f"entities:v1:{self.seed}:{identity}".encode()).hexdigest()
        )

    def location(self, identity, province=None, city=None):
        rows = [
            r
            for r in self.p["locations"]
            if (not province or r["province"] == province)
            and (not city or r["city"] == city)
        ]
        if not rows:
            raise ValueError(f"Hồ sơ không có địa phương khớp tỉnh {province}.")
        return self.rng(identity).choice(rows)

    def person(self, identity, at, province=None):
        r = self.rng(identity)
        location = self.location(identity, province)
        result = {
            "full_name": r.choice(self.p["surnames"])
            + " "
            + r.choice(self.p["given_names"]),
            "email": hashlib.sha256(str(identity).encode()).hexdigest()[:16]
            + "@example.com",
            "phone_number": r.choice(self.p["phone_prefixes"])
            + f"{r.randrange(10**7):07}",
            "province": location["province"],
            "city": location["city"],
            "membership_tier": "Member",
            "registration_date": at,
            "updated_at": at,
        }

        from ..config.configuration import RuntimeConfiguration

        result.update(
            RuntimeConfiguration.attributes(
                self.p.get("customer_attributes", {}), self.seed, identity
            )
        )
        if result.get("date_of_birth") and result["date_of_birth"] > at[:10]:
            raise ValueError("Ngày sinh sau thời điểm mô phỏng.")
        return result

    def seller(self, identity):
        from ..config.configuration import RuntimeConfiguration

        values = RuntimeConfiguration.attributes(
            self.p.get("seller_attributes", {}), self.seed, identity
        )
        location = self.location(identity, values.get("province"), values.get("city"))
        if values.get("city") and values["city"] != location["city"]:
            raise ValueError("Tỉnh/thành phố người bán phải cùng bộ địa phương.")
        return {"province": location["province"], "city": location["city"], **values}

    def address(self, identity, customer=None, province=None, detail=None, at=None):
        location = self.location(identity, province)
        if customer is None and at is None:
            raise ValueError("Cần thời điểm mô phỏng để tạo người nhận vãng lai.")
        person = customer or self.person(identity, at, province)
        return {
            "customer_id": customer["id"] if customer else None,
            "recipient_name": person["full_name"],
            "phone": person["phone_number"],
            "address_detail": detail
            or f"{self.rng(identity).randint(1, 300)} {location['street']}",
            "ward": location["ward"],
            "district": location["district"],
            "province": location["province"],
            "is_default": False,
        }
