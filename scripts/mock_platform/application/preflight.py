"""Read-only guidance: warnings never synthesize business input or change config."""

from sqlalchemy import func, select


class ConfigurationPreflight:
    def __init__(self, service):
        self.s = service

    def check(self, config):
        warnings = []
        channels = set()
        for code, entry in config.items():
            if not entry.get("enabled"):
                continue
            bundles = [
                {**entry.get("params", {}), **v["params"]}
                for v in entry.get("variants", [])
            ] or [entry.get("params", {})]
            if code == "MKT-01":
                channels.update((p.get("campaign_channel") or "WEB") for p in bundles)
        table = self.s.db.bm.tables["marketing_campaigns"]
        with self.s.db.business.connect() as c:
            channels.update(
                c.execute(select(table.c.target_channel_code).distinct()).scalars()
            )
        for code, entry in config.items():
            if not entry.get("enabled"):
                continue
            for variant in entry.get("variants", []) or [{"params": {}}]:
                p = {**entry.get("params", {}), **variant["params"]}
                if (
                    code in ("CUS-WEB-01", "GST-WEB-01")
                    and p.get("campaign") == "auto"
                    and (p.get("channel") or "Web").upper() not in channels
                ):
                    warnings.append(
                        f"{code}: phiên gắn campaign tự động nhưng chưa có cấu hình chiến dịch cùng kênh {p.get('channel', 'Web')}. Kiểm tra cả ngày hiệu lực."
                    )
        legacy = sum(
            bool(e.get("enabled")) and not e.get("actor_pool") for e in config.values()
        )
        if legacy:
            warnings.append(
                f"{legacy} hành động dùng lựa chọn tương thích cũ, chưa khai báo nhóm người thực hiện."
            )
        if any(config.get(code, {}).get("enabled") for code in ("CUS-05", "GST-02")):
            inv = self.s.db.bm.tables["inventory_levels"]
            products = self.s.db.bm.tables["products"]
            with self.s.db.business.connect() as c:
                n = c.execute(select(func.count()).select_from(products)).scalar()
                covered = c.execute(
                    select(func.count(func.distinct(inv.c.sku))).where(
                        inv.c.quantity_on_hand > inv.c.quantity_reserved
                    )
                ).scalar()
            if n and covered < n:
                warnings.append(
                    f"Hiện có tồn khả dụng cho {covered}/{n} SKU. Yêu cầu checkout vẫn có thể bị từ chối; engine không tự bù hàng hoặc tạo đơn."
                )
        return list(dict.fromkeys(warnings))
