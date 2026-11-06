"""Explicit simulation assumptions, not claims about any marketplace's policies."""

from .configuration import DEFAULTS

DEFAULT_POLICY = DEFAULTS["business_policy"]


class BusinessPolicy:
    @staticmethod
    def validate(value):
        if not isinstance(value, dict) or set(value) != set(DEFAULT_POLICY):
            raise ValueError(
                "Chính sách cần return_window_days, payout_hold_days, max_delivery_attempts."
            )
        for key, number in value.items():
            if type(number) is not int or not 1 <= number <= (
                10 if key == "max_delivery_attempts" else 365
            ):
                raise ValueError(f"{key}: số ngày/lần ngoài miền hợp lệ.")
        if value["payout_hold_days"] <= value["return_window_days"]:
            raise ValueError("Giữ tiền đối soát phải dài hơn cửa sổ yêu cầu trả hàng.")
        return dict(value)
