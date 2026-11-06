# ruff: noqa: TRY004
"""Configurable contextual preferences; no category or customer-specific branches."""

from sqlalchemy import select


class TargetPreferences:
    def __init__(self, engine):
        self.e = engine

    @staticmethod
    def validate(spec, tables):
        import math

        if not isinstance(spec, dict):
            raise ValueError("preferences cần object theo bảng.")
        for table, cfg in spec.items():
            if (
                table not in tables
                or not isinstance(cfg, dict)
                or set(cfg) - {"source", "weight", "require"}
            ):
                raise ValueError("Bộ chọn ưu tiên không hợp lệ.")
            if table != "products" or cfg.get("source") not in (
                "session_views",
                "session_interest",
            ):
                raise ValueError("Nguồn ưu tiên chưa được hỗ trợ.")
            w = cfg.get("weight", 1)
            if (
                type(w) not in (int, float)
                or not math.isfinite(w)
                or w <= 0
                or type(cfg.get("require", False)) is not bool
            ):
                raise ValueError("Trọng số ưu tiên phải dương; require cần boolean.")

    def choose(self, table, rows):
        e = self.e
        cfg = e.a.get("preferences", {}).get(table)
        if not cfg:
            pool = e.binding.pending
            if pool and pool.get("sampling"):
                entity = pool["entity"]
                return e.r.choices(
                    rows,
                    weights=[
                        e.binding.weight(
                            pool, e.u.one(entity, e.binding.owner_id(table, r, entity))
                        )
                        for r in rows
                    ],
                    k=1,
                )[0]
            return e.r.choice(rows)
        session = getattr(e, "selected_context", {}).get("sessions")
        if not session:
            from .domain import NotEligible

            raise NotEligible("Ưu tiên sản phẩm cần context phiên đã chọn.")
        if cfg["source"] == "session_views":
            t = e.db.bm.tables["page_events"]
            identities = set(
                e.u.conn.execute(
                    select(t.c.product_id).where(
                        t.c.session_id == session["id"],
                        t.c.event_type == "view_product",
                        t.c.event_time <= e.now,
                    )
                ).scalars()
            )
        else:
            interest = e.getmeta("session_interest:" + str(session["id"]), {})
            identities = {
                r["id"] for r in rows if r["category_id"] == interest.get("category_id")
            }
        if cfg.get("require"):
            rows = [r for r in rows if r["id"] in identities]
            if not rows:
                from .domain import NotEligible

                raise NotEligible("Chưa có sản phẩm phù hợp lịch sử phiên.")
        preferred = [r for r in rows if r["id"] in identities]
        other = [r for r in rows if r["id"] not in identities]
        if preferred and other:
            # Group odds stay constant when the catalog grows beyond the crawl sample.
            group = e.r.choices(
                [preferred, other], weights=[cfg.get("weight", 1), 1], k=1
            )[0]
            return e.r.choice(group)
        return e.r.choice(rows)
