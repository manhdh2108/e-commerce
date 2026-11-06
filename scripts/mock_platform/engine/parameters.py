"""Declarative parameter lookup after actor/target selection; no executable expressions."""

from ..config.configuration import Distribution


class ParameterRules:
    # Filters/identity are chosen by selectors; these fields affect the result of an eligible action.
    RESULT_FIELDS = frozenset(
        {
            "amount",
            "shipping_fee",
            "success_rate",
            "rating",
            "value",
            "reason",
            "carrier",
            "carrier_code",
        }
    )

    @classmethod
    def validate(cls, rules, fields):
        if not isinstance(rules, list) or len(rules) > 1000:
            raise ValueError("parameter_rules cần danh sách tối đa 1.000 quy tắc.")
        for rule in rules:
            if (
                not isinstance(rule, dict)
                or set(rule) != {"when", "params"}
                or not isinstance(rule["when"], dict)
                or not isinstance(rule["params"], dict)
            ):
                raise ValueError("Quy tắc tham số cần when và params.")
            for path, values in rule["when"].items():
                if (
                    not isinstance(path, str)
                    or path.split(".")[0]
                    not in {
                        "actor",
                        "selected",
                        "order",
                        "address",
                        "warehouse",
                        "params",
                    }
                    or not isinstance(values, list)
                    or not values
                ):
                    raise ValueError("Điều kiện lookup không hợp lệ.")
            if set(rule["params"]) - (set(fields) & cls.RESULT_FIELDS):
                raise ValueError(
                    "Lookup chỉ được thay tham số kết quả, không được đổi đối tượng đang xử lý."
                )
            for value in rule["params"].values():
                if isinstance(value, dict):
                    Distribution.validate(value)
                if any(
                    v is None or isinstance(v, (dict, list)) for v in cls.values(value)
                ):
                    raise ValueError("Tham số kết quả cần giá trị đơn không null.")

    @staticmethod
    def values(value):
        if not isinstance(value, dict):
            return [value]
        if value["kind"] in ("integer", "number"):
            return [value["min"], value["max"]]
        if value["kind"] == "choice":
            return value["values"]
        if value["kind"] == "constant":
            return [value["value"]]
        raise ValueError("Tham số hành động không hỗ trợ khoảng ngày.")

    @staticmethod
    def context(engine, table=None, row=None):
        e = engine
        if not hasattr(e, "selected_context"):
            e.selected_context = {}
        if table and row is not None:
            e.selected_context[table] = row
        actor = e.binding.actor or {}
        actor_context = {**actor}
        if actor.get("entity_id") is not None:
            record = e.u.one(actor["entity"], actor["entity_id"]) or {}
            actor_context = {**record, **actor}
        order = e.selected_context.get("orders")
        if not order and "order_items" in e.selected_context:
            order = e.u.one("orders", e.selected_context["order_items"]["order_id"])
        context = {
            "actor": actor_context,
            "selected": e.selected_context,
            "order": order or {},
            "params": e.p,
        }
        if order:
            context["address"] = (
                e.u.one("customer_addresses", order["shipping_address_id"]) or {}
            )
            wid = e.getmeta(f"order:{order['id']}", {}).get("warehouse")
            context["warehouse"] = e.u.one("warehouses", wid) or {} if wid else {}
        if "warehouses" in e.selected_context:
            context["warehouse"] = e.selected_context["warehouses"]
        if "customer_addresses" in e.selected_context:
            context["address"] = e.selected_context["customer_addresses"]
        return context

    @classmethod
    def apply(cls, engine, table=None, row=None):
        e = engine
        context = cls.context(e, table, row)
        for i, rule in enumerate(e.a.get("parameter_rules", [])):
            good = True
            for path, values in rule["when"].items():
                node = context
                for part in path.split("."):
                    if not isinstance(node, dict) or part not in node:
                        good = False
                        break
                    node = node[part]
                if not good or node not in values:
                    good = False
                    break
            if good:
                for key, value in rule["params"].items():
                    resolved = (
                        Distribution.sample(
                            value, e.a.get("seed", 42), f"{e.a['id']}:lookup:{i}:{key}"
                        )
                        if isinstance(value, dict)
                        else value
                    )
                    if (
                        key in ("carrier", "carrier_code")
                        and "carriers" in e.selected_context
                    ):
                        field = "id" if key == "carrier" else "carrier_code"
                        if (
                            resolved
                            and resolved != e.selected_context["carriers"][field]
                        ):
                            from .domain import NotEligible

                            raise NotEligible(
                                "Lookup không được đổi carrier sau khi đã chọn tài nguyên."
                            )
                    e.p[key] = resolved
                return
