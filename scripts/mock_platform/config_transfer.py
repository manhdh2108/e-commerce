"""Validate portable JSON configurations before saving a new version."""

import json
from collections import Counter
from pathlib import Path
from .service import ACTIONS, CATALOG
from .storage import ROOT

MAX_CONFIG_BYTES = 2 * 1024 * 1024
TEMPLATE = ROOT / "docs/mock-design/examples/realistic-current-engine-2026.json"


class ConfigTransfer:
    def __init__(self, service):
        self.s = service

    @staticmethod
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"JSON có khóa bị lặp: {key}.")
            result[key] = value
        return result

    def preview(self, payload):
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Hãy chọn file JSON có nội dung.")
        if len(text.encode("utf-8")) > MAX_CONFIG_BYTES:
            raise ValueError("File JSON tối đa 2 MiB.")
        try:

            def invalid_constant(value):
                raise ValueError(f"JSON có giá trị số không hợp lệ: {value}.")

            data = json.loads(
                text.lstrip("\ufeff"),
                object_pairs_hook=self.unique_object,
                parse_constant=invalid_constant,
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON sai cú pháp tại dòng {exc.lineno}, cột {exc.colno}: {exc.msg}."
            ) from None
        except RecursionError:
            raise ValueError("JSON lồng quá nhiều cấp.") from None
        if not isinstance(data, dict) or not data:
            raise ValueError("Gốc JSON phải là object cấu hình không rỗng.")
        warnings = []
        if "config" in data:
            allowed = {"name", "config", "format", "format_version", "version_id"}
            unknown = set(data) - allowed
            if unknown:
                raise ValueError(
                    "Trường ở gốc không được hỗ trợ: " + ", ".join(sorted(unknown))
                )
            if data.get("format", "mock-studio-config") != "mock-studio-config":
                raise ValueError("Định dạng file không phải mock-studio-config.")
            if (
                type(data.get("format_version", 1)) is not int
                or data.get("format_version", 1) != 1
            ):
                raise ValueError("Chỉ hỗ trợ format_version = 1.")
            config, name = data["config"], data.get("name", "Cấu hình nhập từ JSON")
            if "version_id" in data:
                warnings.append(
                    "Mã cấu hình cũ trong file được bỏ qua; khi lưu sẽ tạo cấu hình mới."
                )
        else:
            config, name = data, "Cấu hình nhập từ JSON"
        name = payload.get("name", name)
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
            raise ValueError("Tên cấu hình phải có từ 1 đến 200 ký tự.")
        config = self.s.validate_config(config)
        normalized = {}
        for code, cfg in config.items():
            # Omitted actions stay disabled; omitted parameters use registry defaults.
            normalized[code] = {
                "enabled": cfg.get("enabled", False),
                "count": cfg.get("count", 0),
                "mode": cfg.get("mode", "count"),
                "special": cfg.get("special", {}),
                "params": {
                    key: value
                    for key, value in cfg.get("params", {}).items()
                    if not (
                        value in ["", None]
                        and next(f for f in ACTIONS[code]["fields"] if f["key"] == key)[
                            "type"
                        ]
                        in ["number", "select"]
                    )
                },
            }
        enabled = [code for code, cfg in normalized.items() if cfg["enabled"]]
        counts = Counter(ACTIONS[code]["system"] for code in enabled)
        all_dates = sorted(
            {day for cfg in normalized.values() for day in cfg["special"]}
        )
        next_day = self.s.summary().get("next_day")
        if all_dates:
            warnings.append(
                "Lịch ngày cụ thể trong file được giữ nguyên, không tự đổi năm hoặc dời theo ngày nhập."
            )
        if next_day and any(day < next_day for day in all_dates):
            warnings.append(
                f"Một số ngày trong file trước ngày chạy tiếp {next_day}; chúng không làm chạy lại dữ liệu cũ."
            )
        warnings.append(
            "Nhập cấu hình chỉ lưu Control DB. Không tự đồng bộ, tạo dữ liệu nền hoặc chạy mock."
        )
        if not enabled:
            warnings.append("Cấu hình không bật hành động nào.")
        return {
            "name": name.strip(),
            "config": normalized,
            "warnings": warnings,
            "summary": {
                "enabled": len(enabled),
                "included": len(normalized),
                "normal_count": sum(
                    c["count"]
                    for c in normalized.values()
                    if c["enabled"] and c["mode"] == "count"
                ),
                "automatic": sum(
                    c["mode"] == "all" for c in normalized.values() if c["enabled"]
                ),
                "systems": [
                    {"key": s["key"], "enabled": counts[s["key"]]} for s in CATALOG
                ],
                "date_start": all_dates[0] if all_dates else None,
                "date_end": all_dates[-1] if all_dates else None,
            },
        }

    def save(self, payload):
        preview = self.preview(payload)
        result = self.s.save_version(
            {"name": preview["name"], "config": preview["config"]}
        )
        return {**result, "name": preview["name"]}

    @staticmethod
    def template_path():
        return Path(TEMPLATE)
