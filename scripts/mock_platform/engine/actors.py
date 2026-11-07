"""Actor identity, role and scope binding; definitions live in environment config."""

from sqlalchemy import func, select

from ..config.configuration import (
    RuntimeConfiguration,
    matches,
    resolve_filters,
    rng,
    sql_filter,
    validate_filters,
)

# Process-local cache of weighted sampling frames, keyed by pool definition.
_SAMPLING_CACHE = {}


class ActorBinding:
    def __init__(self, engine):
        self.e = engine
        self.actor = None
        self.pending = None
        self.session_pool = None

    def bind(self):
        e = self.e
        pool_id = e.a.get("actor_pool")
        if not pool_id:
            return
        from ..application.service import ACTIONS
        from .domain import NotEligible

        pool = next(
            (p for p in e.entities.p.get("actors", []) if p["id"] == pool_id), None
        )
        role = ACTIONS[e.code]["system"] + "/" + ACTIONS[e.code]["group"]
        if (
            not pool
            or role not in pool["roles"]
            or pool["entity"] != ACTIONS[e.code].get("actor_entity", "virtual")
        ):
            raise NotEligible("Nhóm actor không có vai trò thực hiện hành động.")
        self.pool = pool
        table = pool["entity"]
        if table == "virtual":
            if e.code in (
                "VIS-01",
                "GST-WEB-02",
                "GST-WEB-03",
                "GST-WEB-04",
                "GST-WEB-05",
                "GST-WEB-06",
            ) or (e.code == "GST-02" and e.p.get("checkout_mode") == "linked"):
                self.session_pool = pool
                self.scope = pool.get("scope", {})
                return
            identity = f"virtual:{pool_id}:{rng(e.a.get('seed', 42), e.a['id']).randrange(pool.get('count', 1))}"
            entity_id = None
        else:
            t = e.db.bm.tables[table]
            validate_filters(pool.get("where", {}), t.c.keys())
            query = select(t)
            for field, values in pool.get("where", {}).items():
                query = query.where(sql_filter(t.c[field], values))
            count = e.u.conn.execute(
                select(func.count()).select_from(query.subquery())
            ).scalar()
            if not count:
                raise NotEligible("Nhóm actor không có thực thể phù hợp.")
            if table in ("customers", "sellers", "carriers") and (
                e.a.get("automatic")
                or (e.code == "CUS-05" and e.p.get("checkout_mode") == "linked")
                or e.code
                in (
                    "CUS-WEB-02",
                    "CUS-WEB-03",
                    "CUS-WEB-04",
                    "CUS-WEB-05",
                    "CUS-WEB-06",
                    "CUS-07",
                    "CUS-08",
                    "CUS-09",
                )
            ):
                self.pending = pool
                self.scope = pool.get("scope", {})
                return
            if pool.get("sampling"):
                ids, weights = self.sampling_frame(e, t, pool)
                row = {"id": e.r.choices(ids, weights=weights, k=1)[0]}
            else:
                row = (
                    e.u.conn.execute(
                        query.order_by(t.c.id).offset(e.r.randrange(count)).limit(1)
                    )
                    .mappings()
                    .one()
                )
            entity_id = row["id"]
            identity = f"{table}:{entity_id}"
        key = "actor:" + identity
        # Stable attributes survive days and different roles/pools. Config snapshots do not rewrite existing identities.
        self.actor = e.getmeta(key) or {
            "id": identity,
            "entity": table,
            "entity_id": entity_id,
            "attributes": RuntimeConfiguration.attributes(
                pool.get("attributes", {}), e.a.get("seed", 42), identity
            ),
        }
        if e.getmeta(key) is None:
            e.meta(key, self.actor)
        self.scope = pool.get("scope", {})
        for field, values in self.scope.items():
            param = {"warehouse_id": "warehouse", "carrier_id": "carrier"}.get(field)
            if param and e.p.get(param) and e.p[param] not in values:
                raise NotEligible("Tài nguyên nằm ngoài phạm vi được phân công.")
        if table == "sellers":
            if (
                e.code.startswith("SEL-")
                and e.p.get("target")
                and e.code in ("SEL-01", "SEL-02", "SEL-03")
                and str(e.p["target"]) != str(entity_id)
            ):
                raise NotEligible("Seller không được tác động hồ sơ shop khác.")
            e.p["actor"] = entity_id
            if e.code in ("SEL-01", "SEL-02", "SEL-03"):
                e.p["target"] = str(entity_id)
        if table == "customers" and (e.code.startswith("CUS") or e.code == "SYS-03"):
            if (
                e.p.get("target")
                and str(e.p["target"]) != str(entity_id)
                and e.code
                not in (
                    "CUS-WEB-02",
                    "CUS-WEB-03",
                    "CUS-WEB-04",
                    "CUS-WEB-05",
                    "CUS-WEB-06",
                )
            ):
                raise NotEligible("Khách không được tác động đối tượng của khách khác.")
            if e.code in (
                "CUS-01",
                "CUS-02",
                "CUS-03",
                "CUS-04",
                "CUS-05",
                "CUS-WEB-01",
            ):
                e.p["target"] = str(entity_id)

    @staticmethod
    def sampling_frame(e, t, pool):
        """(ids, weights) ordered by id; same result as weighting every full row.

        Only id and the sampling field are read. On PostgreSQL the frame is cached
        per process and reused while an md5 fingerprint of (id, field) is unchanged.
        """
        import json

        spec = pool.get("sampling", {})
        field = spec.get("field")
        cols = [t.c.id] + ([t.c[field]] if field in t.c else [])
        query = select(*cols)
        for name, values in pool.get("where", {}).items():
            query = query.where(sql_filter(t.c[name], values))
        key = (t.name, json.dumps(pool.get("where", {}), sort_keys=True), json.dumps(spec, sort_keys=True))
        fingerprint = None
        if e.u.conn.dialect.name == "postgresql":
            from sqlalchemy import String, cast
            from sqlalchemy.dialects.postgresql import aggregate_order_by

            sub = query.subquery()
            item = cast(sub.c.id, String)
            if len(cols) > 1:
                item = item + ":" + func.coalesce(cast(sub.c[field], String), "")
            fingerprint = tuple(
                e.u.conn.execute(
                    select(
                        func.count(),
                        func.md5(func.string_agg(item, aggregate_order_by(",", sub.c.id))),
                    )
                ).one()
            )
            hit = _SAMPLING_CACHE.get(key)
            if hit and hit[0] == fingerprint:
                return hit[1], hit[2]
        rows = list(e.u.conn.execute(query.order_by(t.c.id)).mappings())
        ids = [r["id"] for r in rows]
        weights = [ActorBinding.weight(pool, r) for r in rows]
        if fingerprint is not None:
            _SAMPLING_CACHE[key] = (fingerprint, ids, weights)
        return ids, weights

    @staticmethod
    def weight(pool, row):
        spec = pool.get("sampling", {})
        return spec.get("weights", {}).get(
            str(row.get(spec.get("field"))), spec.get("default", 1)
        )

    def filters(self, table):
        if not self.actor:
            return {}
        e = self.e
        result = {}
        a = self.actor
        identity = a["entity_id"]
        for key, values in self.scope.items():
            if key in e.db.bm.tables[table].c:
                result[key] = values
        if a["entity"] == "customers":
            if table == "customers":
                result["id"] = [identity]
            elif "customer_id" in e.db.bm.tables[table].c:
                result["customer_id"] = [identity]
        if a["entity"] == "sellers":
            if table == "sellers":
                result["id"] = [identity]
            elif "seller_id" in e.db.bm.tables[table].c:
                result["seller_id"] = [identity]
        if a["entity"] == "carriers" and table == "shipments":
            result["carrier_id"] = [identity]
        return result

    def owner_id(self, table, row, entity):
        if table == entity:
            return row["id"]
        e = self.e
        if table == "returns":
            row = e.u.one("order_items", row["order_item_id"])
            table = "order_items"
        if table in ("order_items", "payments", "refunds"):
            row = e.u.one("orders", row["order_id"])
            table = "orders"
        if table == "shipments" and entity != "carriers":
            row = e.u.lookup("orders", "order_code", row["order_code"])
            table = "orders"
        if table == "orders" and entity == "carriers":
            row = e.u.lookup("shipments", "order_code", row["order_code"])
        if row is None:
            return None
        return row.get(
            {
                "customers": "customer_id",
                "sellers": "seller_id",
                "carriers": "carrier_id",
            }[entity]
        )

    def permits(self, table, row):
        e = self.e
        if not matches(
            row, resolve_filters(e.a.get("selection", {}).get(table, {}), e)
        ):
            return False
        if table in ("sessions", "cart_items") and (
            self.session_pool
            or (
                self.actor
                and self.actor["entity"] == "virtual"
                and e.code.startswith("GST")
            )
        ):
            session_id = row["id"] if table == "sessions" else row["session_id"]
            owner = e.getmeta("session_actor:" + str(session_id), {})
            if self.session_pool and owner.get("pool") != self.session_pool["id"]:
                return False
            if self.actor and owner.get("actor") != self.actor["id"]:
                return False
        scope = getattr(self, "scope", {})
        if (
            table == "warehouses"
            and scope.get("warehouse_id")
            and row["id"] not in scope["warehouse_id"]
        ):
            return False
        if (
            table == "carriers"
            and scope.get("carrier_id")
            and row["id"] not in scope["carrier_id"]
        ):
            return False
        if table == "orders" and scope.get("warehouse_id"):
            warehouse = e.getmeta(f"order:{row['id']}", {}).get("warehouse")
            if warehouse not in scope["warehouse_id"]:
                return False
        if not matches(row, self.filters(table)):
            return False
        if self.pending:
            pool = self.pending
            entity = pool["entity"]
            identity = self.owner_id(table, row, entity)
            if identity is None:
                return False
            actor = e.u.one(entity, identity)
            if not actor or not matches(actor, pool.get("where", {})):
                return False
            return matches(row, {k: v for k, v in self.scope.items() if k in row})
        if not self.actor:
            return True
        if self.actor["entity"] in ("customers", "sellers", "carriers"):
            owner = self.owner_id(table, row, self.actor["entity"])
            relevant = table == self.actor["entity"] or table in (
                "orders",
                "order_items",
                "returns",
                "shipments",
                "payments",
                "refunds",
                "sessions",
                "cart_items",
                "customer_addresses",
            )
            # Some shared resources are deliberately actor-independent.
            if (
                relevant
                and self.actor["entity"] == "carriers"
                and table
                in ("customers", "sessions", "cart_items", "customer_addresses")
            ):
                return True
            if (
                relevant
                and self.actor["entity"] == "sellers"
                and table in ("sessions", "cart_items", "customer_addresses")
            ):
                return True
            if relevant:
                return owner == self.actor["entity_id"]
        return True

    def selected(self, table, row):
        if self.session_pool and table in ("sessions", "cart_items"):
            e = self.e
            pool = self.session_pool
            session_id = row["id"] if table == "sessions" else row["session_id"]
            owner = e.getmeta("session_actor:" + str(session_id), {})
            self.actor = e.getmeta("actor:" + owner["actor"])
            self.session_pool = None
        if not self.pending:
            return
        pool = self.pending
        entity = pool["entity"]
        e = self.e
        identity = self.owner_id(table, row, entity)
        key = f"{entity}:{identity}"
        self.actor = e.getmeta("actor:" + key) or {
            "id": key,
            "entity": entity,
            "entity_id": identity,
            "attributes": RuntimeConfiguration.attributes(
                pool.get("attributes", {}), e.a.get("seed", 42), key
            ),
        }
        if e.getmeta("actor:" + key) is None:
            e.meta("actor:" + key, self.actor)
        self.pending = None

    def execution_record(self):
        if self.actor is None:
            return None
        from ..application.service import ACTIONS

        attributes = self.actor.get("attributes", {})
        label = next(
            (
                attributes[k]
                for k in ("display_name", "process_name", "provider_name")
                if isinstance(attributes.get(k), str)
            ),
            self.actor["id"],
        )
        if self.actor.get("entity_id") is not None:
            row = self.e.u.one(self.actor["entity"], self.actor["entity_id"]) or {}
            field = {
                "customers": "full_name",
                "sellers": "shop_name",
                "carriers": "carrier_name",
            }[self.actor["entity"]]
            label = row.get(field) or label
        return {
            **self.actor,
            "label": label,
            "pool": self.e.a.get("actor_pool"),
            "role": ACTIONS[self.e.code]["system"]
            + "/"
            + ACTIONS[self.e.code]["group"],
            "scope": getattr(self, "scope", {}),
        }
