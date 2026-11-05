"""Validate settings files for filling forms; preview never saves or touches OLTP."""

from .config_transfer import ConfigTransfer
from .entities import EntityProfile
from .policies import BusinessPolicy, DEFAULT_POLICY
from .storage import ROOT


class SettingsTransfer:
    FORMAT = "mock-studio-settings"
    TEMPLATE = ROOT / "docs/mock-design/examples/settings/diverse-ecommerce.json"

    def __init__(self, service):
        self.s = service

    def preview(self, payload):
        data = ConfigTransfer.parse_document(payload)
        if set(data) == set(DEFAULT_POLICY):
            data = {"business_policy": data}
        else:
            if "config" in data:
                raise ValueError(
                    "Đây là cấu hình hành động; hãy nhập trong tab Cấu hình kịch bản."
                )
            allowed = {
                "format",
                "format_version",
                "name",
                "business_policy",
                "entity_profile",
            }
            if set(data) - allowed:
                raise ValueError(
                    "Trường thiết lập không được hỗ trợ: "
                    + ", ".join(sorted(set(data) - allowed))
                )
            if (
                data.get("format") != self.FORMAT
                or type(data.get("format_version")) is not int
                or data["format_version"] != 1
            ):
                raise ValueError(
                    "File thiết lập cần format=mock-studio-settings và format_version=1."
                )
        name = data.get("name", "Thiết lập nhập từ JSON")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
            raise ValueError("Tên thiết lập phải có từ 1 đến 200 ký tự.")
        if not any(key in data for key in ["business_policy", "entity_profile"]):
            raise ValueError("File cần business_policy hoặc entity_profile.")
        result = {
            "name": name.strip(),
            "summary": {},
            "warnings": [
                "Xem trước và điền form chưa lưu. Kiểm tra rồi bấm Lưu chính sách / Lưu hồ sơ tương ứng.",
                "Kế hoạch/job đã tạo và dữ liệu OLTP hiện có được giữ nguyên.",
            ],
        }
        if "business_policy" in data:
            result["business_policy"] = BusinessPolicy.validate(data["business_policy"])
        if "entity_profile" in data:
            p = result["entity_profile"] = EntityProfile.validate(
                data["entity_profile"]
            )
            result["summary"] = {
                "surnames": len(p["surnames"]),
                "given_names": len(p["given_names"]),
                "name_combinations": len(set(p["surnames"]))
                * len(set(p["given_names"])),
                "phone_prefixes": len(p["phone_prefixes"]),
                "locations": len(p["locations"]),
                "provinces": len({r["province"] for r in p["locations"]}),
                "warehouses": len(p["warehouses"]),
                "carriers": len(p["carriers"]),
            }
            result["warnings"].append(
                "Địa phương, tên và thông tin liên hệ là dữ liệu tổng hợp; không coi là địa giới hoặc hồ sơ thật."
            )
            if self.s.db.get("bootstrap", "done"):
                result["warnings"].append(
                    "Môi trường đã tạo dữ liệu nền: danh sách kho/carrier nhập vào chỉ điền và lưu hồ sơ; không thêm/sửa kho, carrier hoặc tồn kho trong OLTP hiện tại."
                )
            result["warnings"].append(
                "Tồn nền là lượng mỗi SKU tại mỗi kho. Thêm kho sẽ tăng tổng tồn khi bootstrap môi trường mới."
            )
        return result
