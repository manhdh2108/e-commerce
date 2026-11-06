"""Behavioral regressions on isolated DBs; never use the user's mock_oltp."""

import copy
import json
import uuid

import pytest
from sqlalchemy import select

from scripts.mock_platform.tests.test_platform import platform, initialize, enqueue  # noqa: F401 — pytest fixture
from scripts.mock_platform.infrastructure.storage import UnitOfWork
from scripts.mock_platform.engine.domain import DomainEngine, NotEligible
from scripts.mock_platform.application.service import ACTIONS
from scripts.mock_platform.diagnostics.validation import BusinessValidator
from scripts.mock_platform.config.config_transfer import ConfigTransfer


def command(s, w, code, at="2026-11-01T12:00:00", **params):
    action = {
        "id": uuid.uuid4().hex,
        "code": code,
        "at": at,
        "seed": 42,
        "entity_profile": s.entity_profile(),
        "business_policy": s.business_policy(),
        "params": {
            **{f["key"]: f.get("default") for f in ACTIONS[code]["fields"]},
            **params,
        },
    }

    def apply(u):
        with s.db.control.connect() as c:
            state = {
                r.id: r.data
                for r in c.execute(
                    select(s.db.records).where(s.db.records.c.kind == "runtime")
                )
            }
        e = DomainEngine(s.db, u, action, state)
        e.execute()
        return {"effects": e.effects}

    w.transact("fixture:" + action["id"], apply)


def test_profiles_reproducible_and_special_replaces_count(platform):
    s, w, _ = platform
    cfg = {
        "GST-WEB-01": {
            "enabled": True,
            "count": 1,
            "special": {"2026-11-01": 40},
            "params": {},
            "variants": [
                {
                    "name": "Điện thoại tự nhiên",
                    "weight": 7,
                    "params": {"device": "Mobile", "traffic": "Organic"},
                },
                {
                    "name": "Máy tính email",
                    "weight": 3,
                    "params": {"device": "Desktop", "traffic": "Email"},
                },
            ],
        }
    }
    initialize(s, w)
    p = ConfigTransfer(s).preview(
        {"text": json.dumps({"format_version": 2, "config": cfg})}
    )
    assert p["config"]["GST-WEB-01"]["variants"] == cfg["GST-WEB-01"]["variants"]
    id = s.save_version({"config": cfg})["id"]
    plan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    assert plan["total"] == 40
    original = copy.deepcopy(plan)
    changed = copy.deepcopy(cfg)
    changed["GST-WEB-01"]["variants"][0]["params"]["device"] = "Tablet"
    s.update_version(id, {"revision": 1, "config": changed, "name": "Edited"})
    assert (
        s.db.get("plans", plan["id"])["config_snapshot"] == original["config_snapshot"]
    )
    # New plan uses edits; deterministic resolver itself preserves old snapshot.
    from scripts.mock_platform.config.profiles import ParameterProfiles

    assert ParameterProfiles.resolve(
        cfg["GST-WEB-01"], {}, 42, "stable"
    ) == ParameterProfiles.resolve(cfg["GST-WEB-01"], {}, 42, "stable")
    newplan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=newplan["id"])
    assert {r["device_type"] for r in s.data("sessions")} == {"Tablet", "Desktop"}
    assert all(
        (r["device_type"], r["traffic_source"])
        in [("Tablet", "Organic"), ("Desktop", "Email")]
        for r in s.data("sessions")
    )
    assert all(
        r["profile"] for r in s.db.list("action_results") if r.get("status") == "DONE"
    )


@pytest.mark.parametrize(
    "variants",
    [
        [],
        [{"name": "x", "weight": 0, "params": {}}],
        [{"name": "x", "weight": True, "params": {}}],
        [{"name": "x", "weight": 1, "params": {"device": "Invalid"}}],
    ],
)
def test_profile_validation_rejects_invalid(platform, variants):
    s, _, _ = platform
    with pytest.raises(ValueError):
        s.save_version(
            {"config": {"GST-WEB-01": {"enabled": True, "variants": variants}}}
        )


@pytest.mark.parametrize(
    "code", ["GST-WEB-05", "GST-WEB-06", "CUS-WEB-05", "CUS-WEB-06"]
)
def test_cross_actor_cart_target_rejected(platform, code):
    s, w, _ = platform
    initialize(s, w)
    other = "CUS" if code.startswith("GST") else "GST"
    command(
        s,
        w,
        other + "-WEB-01",
        target=str(s.data("customers")[0]["id"]) if other == "CUS" else "",
    )
    session = s.data("sessions")[0]
    command(s, w, other + "-WEB-04", target=str(session["id"]))
    cart = s.data("cart_items")[0]
    before = s.data("page_events")
    with pytest.raises(NotEligible):
        command(s, w, code, target=str(cart["id"]))
    assert (
        s.data("page_events") == before
        and s.data("cart_items")[0]["cart_status"] == "Active"
    )


def test_linked_multiline_checkout_consumes_cart_once(platform):
    s, w, _ = platform
    initialize(s, w)
    customer = s.data("customers")[0]
    command(s, w, "CUS-WEB-01", target=str(customer["id"]))
    assert s.data("sessions")[0]["customer_id"] == customer["id"]
    for _ in range(2):
        command(s, w, "CUS-WEB-04", quantity=2)
    command(s, w, "CUS-WEB-06")
    command(s, w, "CUS-05", checkout_mode="linked", method="COD")
    assert len(s.data("orders")) == 1
    assert len(s.data("order_items")) == 2
    assert s.data("orders")[0]["session_id"] == s.data("sessions")[0]["id"]
    assert s.data("inventory_levels")[0]["quantity_reserved"] == 4
    assert {c["cart_status"] for c in s.data("cart_items")} == {"Converted"}
    assert len(s.data("checkout_lines")) == 2
    with pytest.raises(NotEligible):
        command(s, w, "CUS-05", checkout_mode="linked")
    assert len(s.data("orders")) == 1
    assert BusinessValidator(s.db).report()["ok"]


def test_checkout_rollback_on_insufficient_linked_stock(platform):
    s, w, _ = platform
    initialize(s, w)
    command(s, w, "GST-WEB-01")
    command(s, w, "GST-WEB-04", quantity=20)
    command(s, w, "GST-WEB-06")
    with pytest.raises(NotEligible):
        command(s, w, "GST-02", checkout_mode="linked")
    assert (
        not s.data("orders")
        and not s.data("checkouts")
        and not s.data("customer_addresses")
    )
    assert s.data("inventory_levels")[0]["quantity_reserved"] == 0


def complete_order(s, w, method="COD", **params):
    command(s, w, "CUS-05", quantity=3, method=method, **params)
    if method != "COD":
        command(s, w, "PAY-01", at="2026-11-01T13:00:00", success_rate=100)
    for code, hour in [
        ("ORD-01", 14),
        ("DSP-01", 15),
        ("CAR-01", 16),
        ("CAR-02", 17),
        ("CAR-03", 18),
    ]:
        command(s, w, code, at=f"2026-11-01T{hour}:00:00", success_rate=100)
    if method == "COD":
        command(s, w, "CAR-04", at="2026-11-01T19:00:00")


def test_voucher_returns_refunds_and_settlement(platform):
    s, w, _ = platform
    initialize(s, w)
    command(s, w, "FIN-POL-01", scope="all_leaf", rate=5)
    command(s, w, "MKT-03", amount=30000, min_order=100000, limit=1)
    complete_order(s, w, voucher_mode="auto")
    order = s.data("orders")[0]
    assert order["total_discount_amount"] == 30000 and order["final_amount"] == 270000
    assert len(s.data("order_item_promotions")) == 1
    command(s, w, "CUS-08", at="2026-11-02T10:00:00", quantity=1, reason="Sai mô tả")
    command(s, w, "SUP-01", at="2026-11-02T11:00:00")
    command(s, w, "WH-04", at="2026-11-02T12:00:00")
    assert s.data("refunds")[0]["amount"] == 90000
    assert s.data("inventory_levels")[0]["quantity_on_hand"] == 8
    command(s, w, "PAY-02", at="2026-11-02T13:00:00")
    assert s.data("payments")[0]["paid_amount"] == 270000
    with pytest.raises(NotEligible):
        command(s, w, "WH-04", at="2026-11-02T14:00:00")
    with pytest.raises(NotEligible):
        command(s, w, "FIN-REC-01", at="2026-11-03T12:00:00")
    command(s, w, "FIN-REC-01", at="2026-11-10T12:00:00")
    payout = s.data("seller_payouts")[0]
    assert payout["gross_sales"] == 300000 and payout["refund_amount"] == 100000
    assert payout["commission_amount"] == 10000 and payout["payout_amount"] == 190000
    command(s, w, "FIN-REC-02", at="2026-11-10T13:00:00")
    command(s, w, "FIN-PAY-01", at="2026-11-10T14:00:00")
    assert s.data("seller_payouts")[0]["payout_status"] == "Paid"
    with pytest.raises(NotEligible):
        command(s, w, "FIN-REC-01", at="2026-11-11T12:00:00")
    assert BusinessValidator(s.db).report()["ok"]


def test_failed_delivery_receipt_refunds_without_double_stock(platform):
    s, w, _ = platform
    initialize(s, w)
    command(s, w, "CUS-05", method="Momo", quantity=2)
    command(s, w, "PAY-01", at="2026-11-01T13:00:00", success_rate=100)
    for code, hour in [
        ("ORD-01", 14),
        ("DSP-01", 15),
        ("CAR-01", 16),
        ("CAR-02", 17),
        ("CAR-03", 18),
    ]:
        command(s, w, code, at=f"2026-11-01T{hour}:00:00", success_rate=0)
    assert s.data("inventory_levels")[0]["quantity_on_hand"] == 8
    command(s, w, "CAR-05", at="2026-11-02T10:00:00")
    assert s.data("inventory_levels")[0]["quantity_on_hand"] == 10
    assert s.data("refunds")[0]["amount"] == 200000
    command(s, w, "PAY-02", at="2026-11-02T11:00:00")
    with pytest.raises(NotEligible):
        command(s, w, "CAR-05", at="2026-11-02T12:00:00")
    assert s.data("orders")[0]["order_status"] == "Cancelled"
    assert BusinessValidator(s.db).report()["ok"]


def test_delayed_dispatch_and_pickup_across_days(platform):
    s, w, _ = platform
    initialize(s, w)
    config = {
        c: {"enabled": True, "mode": "all", "params": {}}
        for c in ["ORD-01", "DSP-01", "CAR-01", "CAR-02", "CAR-03", "CAR-04"]
    }
    config["CUS-05"] = {
        "enabled": True,
        "count": 0,
        "special": {"2026-11-01": 1},
        "params": {"method": "COD"},
    }
    config["DSP-01"]["delay_days"] = 1
    config["CAR-01"]["delay_days"] = 1
    config["CAR-03"]["params"]["success_rate"] = 100
    id = s.save_version({"config": config})["id"]
    plan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-03"})
    enqueue(s, w, "run", plan=plan["id"])
    ship = s.data("shipments")[0]
    assert ship["created_at"].startswith("2026-11-02") and ship["picked_at"].startswith(
        "2026-11-03"
    )
    assert s.data("orders")[0]["order_status"] == "Completed"
    assert s.summary()["last_day"] == "2026-11-03"


def test_entity_profiles_and_default_address_switch(platform):
    s, w, _ = platform
    p = s.entity_profile()
    p["warehouses"].append(
        {
            **p["warehouses"][0],
            "warehouse_code": "WH-NORTH",
            "warehouse_name": "Kho Bắc",
            "province": "Hà Nội",
            "city": "Hà Nội",
        }
    )
    p["carriers"].append({"carrier_code": "SECOND", "carrier_name": "Vận chuyển số 2"})
    s.save_entity_profile(p)
    initialize(s, w)
    assert (
        len(s.data("warehouses")) == 2
        and len(s.data("carriers")) == 2
        and len(s.data("inventory_levels")) == 2
    )
    assert len({c["phone_number"] for c in s.data("customers")}) > 1
    customer = s.data("customers")[0]
    command(s, w, "CUS-03", target=str(customer["id"]))
    command(s, w, "CUS-03", target=str(customer["id"]))
    for _ in range(5):
        command(s, w, "CUS-04", target=str(customer["id"]))
    assert sum(a["is_default"] for a in s.data("customer_addresses")) == 1
    before = s.data("customer_addresses")
    command(s, w, "CUS-05", target=str(customer["id"]))
    assert s.data("customer_addresses") == before


def test_multiseller_checkout_and_all_or_nothing_stock(platform):
    s, w, _ = platform
    initialize(s, w)

    def add_second(u):
        seller = dict(u.one("sellers", 7))
        seller["id"] = 8
        seller["shop_name"] = "Shop thứ hai"
        u.add("sellers", **seller)
        product = dict(u.one("products", 123))
        product.update(id=124, sku="00124", seller_id=8)
        u.add("products", **product)
        u.add(
            "inventory_levels",
            warehouse_id=1,
            sku="00124",
            quantity_on_hand=5,
            quantity_reserved=0,
        )
        u.add(
            "inventory_movements",
            warehouse_id=1,
            sku="00124",
            movement_type="Import",
            quantity_change=5,
            movement_date="2026-11-01T00:00:00",
        )

    w.transact("second-seller", add_second)
    command(s, w, "CUS-WEB-01")
    command(s, w, "CUS-WEB-04", product="123", quantity=1)
    command(s, w, "CUS-WEB-04", product="124", quantity=2)
    command(s, w, "CUS-WEB-06")
    command(s, w, "CUS-05", checkout_mode="linked")
    assert len(s.data("orders")) == 2 and len(s.data("checkouts")) == 1
    assert {o["seller_id"] for o in s.data("orders")} == {7, 8}
    assert all(
        o["checkout_id"] == s.data("checkouts")[0]["id"] for o in s.data("orders")
    )
    assert BusinessValidator(s.db).report()["ok"]


def test_paid_cancel_creates_refund_and_releases_voucher(platform):
    s, w, _ = platform
    initialize(s, w)
    command(s, w, "MKT-03", amount=10000)
    command(s, w, "CUS-05", method="Momo", voucher_mode="auto")
    command(s, w, "PAY-01", success_rate=100)
    command(s, w, "CUS-07")
    assert s.data("refunds")[0]["amount"] == 90000
    assert s.data("promotion_usages")[0]["usage_status"] == "Released"
    assert s.data("inventory_levels")[0]["quantity_reserved"] == 0
    command(s, w, "PAY-02")
    assert s.data("payments")[0]["paid_amount"] == 90000
    assert BusinessValidator(s.db).report()["ok"]


def test_validator_catches_actor_corruption_and_arithmetic(platform):
    s, w, _ = platform
    initialize(s, w)
    command(s, w, "CUS-WEB-01")
    session = s.data("sessions")[0]
    with s.db.business.begin() as conn:
        u = UnitOfWork(s.db, conn)
        event = u.add(
            "page_events",
            session_id=session["id"],
            event_type="begin_checkout",
            event_time="2026-11-01T12:00:00",
        )
    s.db.put(
        "action_results",
        "corrupt",
        {"job": "bad", "code": "GST-WEB-06", "status": "DONE"},
    )
    s.db.put(
        "manifests", "corrupt", {"changes": [{"table": "page_events", "after": event}]}
    )
    report = BusinessValidator(s.db).report()
    assert not report["ok"] and any(
        e.get("action") == "GST-WEB-06" for e in report["errors"]
    )
    assert BusinessValidator(s.db).report(job="new")["ok"]


def test_migration_additive_idempotent_and_preflight(platform):
    from scripts.mock_platform.infrastructure.migrations import SchemaMigration

    s, w, _ = platform
    initialize(s, w)
    migration = SchemaMigration(s.db)
    before = s.data("products")
    p = migration.preview()
    assert not p["new_tables"] and not p["new_columns"] and not p["constraints"]
    migration.apply()
    migration.apply()
    assert s.data("products") == before


def test_policy_snapshot_prevents_late_return_after_settlement(platform):
    s, w, _ = platform
    initialize(s, w)
    complete_order(s, w)
    p = s.business_policy()
    p.update(return_window_days=20, payout_hold_days=21)
    s.save_business_policy(p)
    with pytest.raises(NotEligible):
        command(s, w, "CUS-08", at="2026-11-10T12:00:00")


def test_new_scenario_runs_linked_journeys_returns_and_backlog(platform):
    from scripts.mock_platform.config.upgraded_scenario import UpgradedScenario

    s, w, _ = platform
    from scripts.mock_platform.config.settings_transfer import SettingsTransfer
    from scripts.mock_platform.resources import PROJECT_ROOT
    settings = json.loads((PROJECT_ROOT / 'docs/mock-design/examples/settings/diverse-ecommerce.json').read_text())
    preview = SettingsTransfer(s).preview({'text':json.dumps(settings)})
    s.save_entity_profile(preview['entity_profile'])
    s.save_business_policy(preview['business_policy'])
    enqueue(s, w, "sync", preview=s.source_preview({})["id"])
    enqueue(s, w, "bootstrap", customers=30, stock=3000)
    document = UpgradedScenario().build()
    # Keep the full 20-day cohort including delivery plus payout hold, at reduced load.
    for cfg in document["config"].values():
        if cfg.get("mode") != "all":
            cfg["count"] = max(1, cfg["count"] // 10) if cfg["count"] else 0
            cfg["special"] = {
                day: max(1, n // 10) if n else 0
                for day, n in cfg.get("special", {}).items()
            }
    id = ConfigTransfer(s).save({"text": json.dumps(document)})["id"]
    plan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-20"})
    enqueue(s, w, "run", plan=plan["id"])
    assert s.data("orders") and all(o["session_id"] for o in s.data("orders"))
    assert len({r["device_type"] for r in s.data("sessions")}) >= 2
    assert s.data("promotion_usages") and s.data("order_item_promotions")
    assert s.data("refunds") and s.data("seller_payout_items")
    assert any(r["status"] == "Refunded" for r in s.data("returns"))
    assert any(o["order_status"] != "Completed" for o in s.data("orders"))
    report = BusinessValidator(s.db).report()
    assert report["ok"], report["errors"][:5]


def test_legacy_missing_snapshot_is_not_manufactured_on_edit(platform):
    s, _, _ = platform
    id = s.save_version({"config": {"GST-01": {"enabled": True, "count": 2}}})["id"]
    plan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    legacy = s.db.get("plans", plan["id"])
    legacy.pop("config_snapshot")
    s.db.put("plans", plan["id"], legacy)
    s.update_version(id, {"revision": 1, "config": {}, "name": "New"})
    assert "config_snapshot" not in s.db.get("plans", plan["id"])
    with pytest.raises(ValueError, match="snapshot|legacy|Legacy"):
        s.execution_plan(plan["id"])


def test_plan_snapshots_entity_policy_and_recovery_watermark(platform):
    s, w, _ = platform
    entities = s.entity_profile()
    entities["surnames"] = ["Họ tổng hợp"]
    s.save_entity_profile(entities)
    policy = s.business_policy()
    policy.update(return_window_days=3, payout_hold_days=4)
    s.save_business_policy(policy)
    id = s.save_version({"config": {"GST-01": {"enabled": True, "count": 1}}})["id"]
    plan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    assert plan["entity_profile"] == entities and plan["business_policy"] == policy
    changed = copy.deepcopy(entities)
    changed["surnames"] = ["Đã sửa"]
    s.save_entity_profile(changed)
    enqueue(s, w, "run", plan=plan["id"])
    assert s.data("customers")[0]["full_name"].startswith("Họ tổng hợp ")
    sequences = [
        r["commit_sequence"] for r in s.db.list("receipts") if r["status"] == "DONE"
    ]
    assert len(sequences) == len(set(sequences))


def test_postgres_migration_from_27_tables_preserves_ids_and_prices(platform):
    from sqlalchemy import MetaData,Table,Column,inspect
    from scripts.mock_platform.infrastructure.migrations import SchemaMigration
    from pathlib import Path
    s,_,_=platform
    if s.db.business.dialect.name!='postgresql':pytest.skip('DDL migration is PostgreSQL-specific')
    # Only the isolated, empty fixture database is rebuilt as a legacy schema.
    s.db.bm.drop_all(s.db.business)
    legacy=MetaData()
    definitions=json.loads((Path(__file__).parent/'fixtures/schema_v1.json').read_text())
    for name,cols in definitions.items():
        Table(name,legacy,*[Column(col['name'],s.db.bm.tables[name].c[col['name']].type,primary_key=col['name']=='id') for col in cols])
    legacy.create_all(s.db.business)
    with s.db.business.begin() as c:
        c.execute(legacy.tables['products'].insert().values(id=987654321,sku='LEGACY-SKU',name='Sản phẩm giữ nguyên',price=123456))
    migration=SchemaMigration(s.db)
    preview=migration.preview()
    assert len(preview['new_tables'])==6 and preview['new_columns']
    migration.apply()
    assert len(inspect(s.db.business).get_table_names())==33
    row=s.data('products')[0]
    assert row['id']==987654321 and row['price']==123456 and row['sku']=='LEGACY-SKU'
    assert not migration.preview()['new_columns'] and not migration.preview()['constraints']
    migration.apply()
