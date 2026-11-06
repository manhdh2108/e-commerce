# ruff: noqa: TRY004
"""Typed, deterministic configuration primitives. No executable config or domain rules."""

import copy
import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta

from ..resources import RESOURCE_ROOT

DEFAULTS = json.loads((RESOURCE_ROOT / "defaults.json").read_text())


def rng(seed, identity):
    return random.Random(
        hashlib.sha256(f"configuration:v1:{seed}:{identity}".encode()).hexdigest()
    )


class Distribution:
    @staticmethod
    def validate(spec):
        if not isinstance(spec, dict) or "kind" not in spec:
            raise ValueError(
                "Thuộc tính cần kind: choice, integer, number, date hoặc constant."
            )
        kind = spec["kind"]
        allowed = {
            "constant": {"kind", "value"},
            "pattern": {"kind", "value"},
            "choice": {"kind", "values", "weights"},
            "integer": {"kind", "min", "max"},
            "number": {"kind", "min", "max"},
            "date": {"kind", "min", "max"},
        }
        if kind not in allowed or set(spec) - (allowed[kind] | {"null_rate"}):
            raise ValueError("Loại hoặc khóa phân bố không được hỗ trợ.")
        null = spec.get("null_rate", 0)
        if (
            type(null) not in (int, float)
            or not math.isfinite(null)
            or not 0 <= null <= 1
        ):
            raise ValueError("null_rate phải từ 0 đến 1.")
        if kind == "pattern":
            import re

            pattern = spec.get("value")
            if not isinstance(pattern, str) or not 1 <= len(pattern) <= 200:
                raise ValueError("pattern cần chuỗi 1..200 ký tự.")
            for token in re.findall(r"\{([^{}]+)\}", pattern):
                if not re.fullmatch(
                    r"(digits|letters|token):([1-9]|[1-2][0-9]|3[0-2])", token
                ):
                    raise ValueError("pattern chỉ hỗ trợ digits/letters/token:1..32.")
            stripped = re.sub(r"\{[^{}]+\}", "", pattern)
            if "{" in stripped or "}" in stripped:
                raise ValueError("pattern có dấu ngoặc không hợp lệ.")
        if kind == "constant" and "value" not in spec:
            raise ValueError("constant cần value.")
        if kind == "choice":
            values = spec.get("values")
            weights = spec.get("weights", [1] * len(values or []))
            if (
                not isinstance(values, list)
                or not values
                or len(values) > 10000
                or not isinstance(weights, list)
                or len(weights) != len(values)
                or any(
                    type(w) not in (int, float) or not math.isfinite(w) or w <= 0
                    for w in weights
                )
            ):
                raise ValueError(
                    "choice cần danh sách giá trị và trọng số dương tương ứng."
                )
        if kind == "choice" and not math.isfinite(sum(weights)):
            raise ValueError("Tổng trọng số không hợp lệ.")
        if kind in ("integer", "number"):
            for k in ("min", "max"):
                v = spec.get(k)
                if type(v) not in (
                    (int,) if kind == "integer" else (int, float)
                ) or not math.isfinite(v):
                    raise ValueError("Khoảng số không hợp lệ.")
            if spec["min"] > spec["max"]:
                raise ValueError("min phải <= max.")
        if kind == "date" and date.fromisoformat(spec["min"]) > date.fromisoformat(
            spec["max"]
        ):
            raise ValueError("Khoảng ngày không hợp lệ.")
        return copy.deepcopy(spec)

    @classmethod
    def sample(cls, spec, seed, identity):
        r = rng(seed, identity)
        if r.random() < spec.get("null_rate", 0):
            return None
        k = spec["kind"]
        if k == "pattern":
            import re
            import string

            def replace(match):
                token, count = match.group(1).split(":")
                count = int(count)
                alphabet = (
                    string.digits
                    if token == "digits"
                    else string.ascii_lowercase
                    if token == "letters"
                    else string.ascii_lowercase + string.digits
                )
                return "".join(r.choice(alphabet) for _ in range(count))

            return re.sub(r"\{([^{}]+)\}", replace, spec["value"])
        if k == "constant":
            return copy.deepcopy(spec["value"])
        if k == "choice":
            return copy.deepcopy(
                r.choices(spec["values"], weights=spec.get("weights"), k=1)[0]
            )
        if k == "integer":
            return r.randint(spec["min"], spec["max"])
        if k == "number":
            return round(r.uniform(spec["min"], spec["max"]), 6)
        lo, hi = date.fromisoformat(spec["min"]), date.fromisoformat(spec["max"])
        return (lo + timedelta(days=r.randint(0, (hi - lo).days))).isoformat()


def validate_filters(filters, columns, allow_refs=False):
    if not isinstance(filters, dict) or set(filters) - set(columns):
        raise ValueError("Bộ lọc có trường không được hỗ trợ.")
    for value in filters.values():
        if (
            allow_refs
            and isinstance(value, dict)
            and set(value) == {"ref"}
            and isinstance(value["ref"], str)
            and value["ref"].split(".")[0]
            in {"actor", "selected", "order", "address", "warehouse", "params"}
        ):
            continue
        if (
            not isinstance(value, list)
            or not value
            or any(
                type(v) not in (str, int, float, bool, type(None))
                or (type(v) is float and not math.isfinite(v))
                for v in value
            )
        ):
            raise ValueError(
                "Bộ lọc cần danh sách giá trị hoặc tham chiếu context được hỗ trợ."
            )


def resolve_filters(filters, engine):
    if not any(isinstance(v, dict) for v in filters.values()):
        return filters
    from ..engine.domain import NotEligible
    from ..engine.parameters import ParameterRules

    context = ParameterRules.context(engine)
    result = {}
    for field, value in filters.items():
        if not isinstance(value, dict):
            result[field] = value
            continue
        node = context
        for key in value["ref"].split("."):
            if not isinstance(node, dict) or key not in node:
                raise NotEligible("Chưa có context để chọn đối tượng: " + value["ref"])
            node = node[key]
        result[field] = node if isinstance(node, list) else [node]
    try:
        validate_filters(result, result.keys())
    except ValueError as exc:
        raise NotEligible(str(exc)) from exc
    return result


def sql_filter(column, values):
    """SQL IN with explicit NULL semantics matching the in-memory predicate."""
    from sqlalchemy import or_

    present = [v for v in values if v is not None]
    return (
        or_(column.in_(present), column.is_(None))
        if None in values
        else column.in_(present)
    )


def matches(row, filters):
    return all(row.get(k) in values for k, values in filters.items())


class RuntimeConfiguration:
    # Business fields intentionally typed; arbitrary profile attributes stay in Control DB.
    CUSTOMER_FIELDS = frozenset({"gender", "date_of_birth", "membership_tier", "email"})
    SELLER_FIELDS = frozenset(
        {"phone", "shop_name", "seller_name", "email", "province", "city", "tier"}
    )
    EXTRAS = frozenset(
        {
            "customer_attributes",
            "seller_attributes",
            "actors",
            "inventory",
            "channels",
            "payment_methods",
            "bootstrap",
        }
    )

    @classmethod
    def validate(cls, profile):
        for section, fields in [
            ("customer_attributes", cls.CUSTOMER_FIELDS),
            ("seller_attributes", cls.SELLER_FIELDS),
        ]:
            specs = profile.get(section, {})
            if not isinstance(specs, dict) or set(specs) - fields:
                raise ValueError(f"{section}: trường không hỗ trợ.")
            for field, spec in specs.items():
                Distribution.validate(spec)
                if field not in ("gender", "date_of_birth", "phone") and (
                    spec.get("null_rate", 0)
                    or any(
                        v is None
                        for v in spec.get("values", [spec.get("value")])
                        if spec["kind"] in ("constant", "choice")
                    )
                ):
                    raise ValueError(f"{field}: thuộc tính bắt buộc không được null.")
                if field == "date_of_birth" and spec["kind"] not in (
                    "date",
                    "constant",
                    "choice",
                ):
                    raise ValueError("Ngày sinh cần kiểu ngày.")
                if field != "date_of_birth" and spec["kind"] not in (
                    "constant",
                    "choice",
                    "pattern",
                ):
                    raise ValueError(f"{field}: cần constant hoặc choice.")
                if field == "date_of_birth":
                    values = (
                        [spec["min"], spec["max"]]
                        if spec["kind"] == "date"
                        else spec.get("values", [spec.get("value")])
                    )
                    for v in values:
                        if v is not None:
                            date.fromisoformat(v)
                else:
                    for v in spec.get("values", [spec.get("value")]):
                        if v is not None and (not isinstance(v, str) or not v.strip()):
                            raise ValueError(f"{field}: cần chuỗi hoặc null.")
        seller = profile.get("seller_attributes", {})
        possibilities = lambda spec: (
            set(spec.get("values", [spec.get("value")])) if spec else {None}
        )
        for province in possibilities(seller.get("province")):
            for city in possibilities(seller.get("city")):
                if not any(
                    (province is None or row["province"] == province)
                    and (city is None or row["city"] == city)
                    for row in profile["locations"]
                ):
                    raise ValueError(
                        "Bộ tỉnh/thành phố người bán không khớp hồ sơ địa phương; hãy dùng bộ nhất quán."
                    )
        baseline = profile.get("bootstrap", {})
        if not isinstance(baseline, dict) or set(baseline) - {"customer_history_days"}:
            raise ValueError("bootstrap chỉ hỗ trợ customer_history_days.")
        if "customer_history_days" in baseline:
            spec = baseline["customer_history_days"]
            Distribution.validate(spec)
            if (
                spec["kind"] != "integer"
                or spec["min"] < 0
                or spec["max"] > 36500
                or spec.get("null_rate", 0)
            ):
                raise ValueError(
                    "Tuổi tài khoản nền cần khoảng số nguyên 0..36500 ngày."
                )
        actors = profile.get("actors", [])
        if not isinstance(actors, list):
            raise ValueError("actors cần danh sách hồ sơ.")
        ids = set()
        for pool in actors:
            if not isinstance(pool, dict) or set(pool) - {
                "id",
                "roles",
                "entity",
                "count",
                "where",
                "attributes",
                "scope",
                "sampling",
                "availability",
            }:
                raise ValueError("Hồ sơ actor có khóa không được hỗ trợ.")
            if (
                not isinstance(pool.get("id"), str)
                or not pool["id"]
                or len(pool["id"]) > 100
                or pool["id"] in ids
            ):
                raise ValueError("ID nhóm actor thiếu hoặc trùng.")
            ids.add(pool["id"])
            if pool.get("entity") not in (
                "customers",
                "sellers",
                "carriers",
                "virtual",
            ):
                raise ValueError("Loại actor không hợp lệ.")
            if (
                not isinstance(pool.get("roles"), list)
                or not pool["roles"]
                or any(not isinstance(r, str) for r in pool["roles"])
            ):
                raise ValueError("Actor cần danh sách vai trò.")
            from ..application.service import CATALOG

            roles = {s["key"] + "/" + a["group"] for s in CATALOG for a in s["actions"]}
            if set(pool["roles"]) - roles:
                raise ValueError(
                    "Vai trò actor không tồn tại trong danh mục hành động."
                )
            expected = {
                s["key"] + "/" + a["group"]: a.get("actor_entity", "virtual")
                for s in CATALOG
                for a in s["actions"]
            }
            if any(expected[r] != pool["entity"] for r in pool["roles"]):
                raise ValueError("Loại thực thể không phù hợp vai trò actor.")
            import json

            schema = json.loads((RESOURCE_ROOT / "business_schema.json").read_text())
            if "availability" in pool:
                a = pool["availability"]
                if not isinstance(a, dict) or set(a) != {"start", "end"}:
                    raise ValueError("availability cần start/end.")
                ActionSchedule.validate(a)
            if "sampling" in pool:
                sample = pool["sampling"]
                if (
                    pool["entity"] == "virtual"
                    or not isinstance(sample, dict)
                    or set(sample) - {"field", "weights", "default"}
                ):
                    raise ValueError(
                        "sampling cần thực thể OLTP và bộ trọng số hợp lệ."
                    )
                if sample.get("field") not in [
                    f["name"] for f in schema[pool["entity"]]
                ] or not isinstance(sample.get("weights"), dict):
                    raise ValueError("sampling cần field thật và weights object.")
                if any(
                    type(w) not in (int, float) or not math.isfinite(w) or w <= 0
                    for w in [*sample["weights"].values(), sample.get("default", 1)]
                ):
                    raise ValueError("Trọng số thực thể phải hữu hạn và dương.")
            if pool["entity"] != "virtual":
                validate_filters(
                    pool.get("where", {}), [f["name"] for f in schema[pool["entity"]]]
                )
            validate_filters(
                pool.get("scope", {}),
                {"warehouse_id", "carrier_id", "seller_id", "customer_id"},
            )
            if any(
                type(v) is not int or v < 1
                for values in pool.get("scope", {}).values()
                for v in values
            ):
                raise ValueError("Phạm vi phân công cần ID nguyên dương.")
            if (
                type(pool.get("count", 1)) is not int
                or not 1 <= pool.get("count", 1) <= 100000
            ):
                raise ValueError("Quy mô actor ngoài miền hỗ trợ.")
            if not isinstance(pool.get("attributes", {}), dict):
                raise ValueError("attributes cần object.")
            for spec in pool.get("attributes", {}).values():
                Distribution.validate(spec)
            for key in ("where", "scope"):
                if not isinstance(pool.get(key, {}), dict) or any(
                    not isinstance(v, list) or not v for v in pool.get(key, {}).values()
                ):
                    raise ValueError("Bộ lọc actor cần danh sách giá trị.")
            if pool["entity"] == "virtual" and pool.get("where"):
                raise ValueError("Actor ảo không có bộ lọc OLTP.")
        inv = profile.get("inventory", [])
        if not isinstance(inv, list):
            raise ValueError("inventory cần danh sách quy tắc.")
        for rule in inv:
            if (
                not isinstance(rule, dict)
                or set(rule) - {"products", "warehouses", "quantity", "coverage"}
                or "quantity" not in rule
            ):
                raise ValueError("Quy tắc tồn không hợp lệ.")
            validate_filters(
                rule.get("products", {}),
                {"id", "sku", "category_id", "seller_id", "brand_name", "type"},
            )
            validate_filters(
                rule.get("warehouses", {}), {"warehouse_code", "province", "city"}
            )
            Distribution.validate(rule["quantity"])
            spec = rule["quantity"]
            candidates = (
                spec.get("values", [spec.get("value")])
                if spec["kind"] in ("choice", "constant")
                else [spec.get("min"), spec.get("max")]
            )
            if (
                spec["kind"] not in ("integer", "choice", "constant")
                or spec.get("null_rate", 0)
                or any(type(q) is not int or q < 0 for q in candidates)
            ):
                raise ValueError("Tồn phải là số nguyên không âm.")
            cov = rule.get("coverage", 1)
            if (
                type(cov) not in (int, float)
                or not math.isfinite(cov)
                or not 0 <= cov <= 1
            ):
                raise ValueError("coverage phải từ 0 đến 1.")
        for section, fields in [
            ("channels", {"channel_name", "channel_type"}),
            ("payment_methods", {"method_name", "method_group"}),
        ]:
            if section in profile:
                rows = profile[section]
                if (
                    not isinstance(rows, list)
                    or not rows
                    or any(
                        not isinstance(r, dict)
                        or set(r) != fields
                        or any(
                            not isinstance(v, str) or not v.strip() for v in r.values()
                        )
                        for r in rows
                    )
                ):
                    raise ValueError(f"{section}: bản ghi không hợp lệ.")
                key = "channel_name" if section == "channels" else "method_name"
                if len({r[key] for r in rows}) != len(rows):
                    raise ValueError(f"{section}: trùng tên.")
                if section == "payment_methods" and any(
                    r["method_group"]
                    not in ("COD", "E-Wallet", "Card", "Bank Transfer")
                    for r in rows
                ):
                    raise ValueError("Nhóm thanh toán chưa có semantics.")
        return profile

    @staticmethod
    def attributes(specs, seed, identity):
        return {
            k: Distribution.sample(v, seed, f"{identity}:{k}") for k, v in specs.items()
        }


class ActionSchedule:
    @staticmethod
    def validate(spec):
        if (
            not isinstance(spec, dict)
            or set(spec)
            - {
                "start",
                "end",
                "duration_seconds",
                "offset_seconds",
                "after_seconds",
                "windows",
            }
            or (
                not {"start", "end"} <= set(spec)
                and "offset_seconds" not in spec
                and "after_seconds" not in spec
                and "windows" not in spec
            )
        ):
            raise ValueError("schedule cần start/end HH:MM:SS.")
        from datetime import time

        lo, hi = (
            time.fromisoformat(spec.get("start", "00:00:00")),
            time.fromisoformat(spec.get("end", "23:59:59")),
        )
        if lo.tzinfo or hi.tzinfo or lo.microsecond or hi.microsecond or lo > hi:
            raise ValueError("Khung giờ không múi giờ, theo giây và trong cùng ngày.")
        if "windows" in spec:
            windows = spec["windows"]
            if not isinstance(windows, list) or not 1 <= len(windows) <= 48:
                raise ValueError("windows cần 1..48 khung giờ có trọng số.")
            for window in windows:
                if not isinstance(window, dict) or set(window) != {
                    "start",
                    "end",
                    "weight",
                }:
                    raise ValueError("Khung giờ cần start/end/weight.")
                ActionSchedule.validate({k: window[k] for k in ("start", "end")})
                if (
                    type(window["weight"]) not in (int, float)
                    or not math.isfinite(window["weight"])
                    or window["weight"] <= 0
                ):
                    raise ValueError("Trọng số giờ phải dương.")
        for key in ("duration_seconds", "offset_seconds", "after_seconds"):
            if key not in spec:
                continue
            Distribution.validate(spec[key])
            d = spec[key]
            if (
                d["kind"] != "integer"
                or d["min"] < 1
                or d["max"] > (31 * 86400 if key == "after_seconds" else 86400)
                or d.get("null_rate", 0)
            ):
                raise ValueError("Thời lượng phiên cần integer 1..86400 giây.")

    @staticmethod
    def at(day, spec, seed, identity):
        if spec.get("windows"):
            spec = rng(seed, identity + ":window").choices(
                spec["windows"], weights=[w["weight"] for w in spec["windows"]], k=1
            )[0]
        lo = datetime.fromisoformat(day + "T" + spec.get("start", "00:00:00"))
        hi = datetime.fromisoformat(day + "T" + spec.get("end", "23:59:59"))
        return (
            lo
            + timedelta(
                seconds=rng(seed, identity).randint(0, int((hi - lo).total_seconds()))
            )
        ).isoformat(timespec="seconds")
