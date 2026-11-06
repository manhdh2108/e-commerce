# ruff: noqa: F811
"""Configuration behavior on disposable DBs; never modify the live mock database."""

import copy
import json

import pytest

from scripts.mock_platform.config.config_transfer import ConfigTransfer
from scripts.mock_platform.config.configuration import Distribution
from scripts.mock_platform.engine.domain import NotEligible
from scripts.mock_platform.engine.entities import DEFAULT_PROFILE, EntityProfile
from scripts.mock_platform.application.service import ACTIONS
from scripts.mock_platform.tests.test_engine_v2 import command
from scripts.mock_platform.tests.test_platform import (
    enqueue,
    initialize,
    platform,  # noqa: F401
)


def profile(**extra):
    return {**copy.deepcopy(DEFAULT_PROFILE), **extra}


def role(code):
    return ACTIONS[code]["system"] + "/" + ACTIONS[code]["group"]


def test_invalid_attributes_are_not_ignored():
    with pytest.raises(ValueError):
        EntityProfile.validate(
            profile(customer_attributes={"unknown": {"kind": "constant", "value": "x"}})
        )
    with pytest.raises(ValueError):
        EntityProfile.validate(
            profile(inventory=[{"quantity": {"kind": "integer", "min": -1, "max": 10}}])
        )
    with pytest.raises(ValueError):
        EntityProfile.validate(
            profile(
                seller_attributes={
                    "province": {"kind": "constant", "value": "Không có trong hồ sơ"}
                }
            )
        )
    with pytest.raises(ValueError):
        Distribution.validate(
            {"kind": "choice", "values": ["a"], "weights": [float("nan")]}
        )


def test_attributes_and_sparse_inventory_are_configured(platform):
    s, w, _ = platform
    p = profile(
        customer_attributes={
            "gender": {
                "kind": "choice",
                "values": ["Female", "Male"],
                "weights": [1, 3],
            },
            "date_of_birth": {"kind": "date", "min": "1980-01-01", "max": "2000-12-31"},
        },
        inventory=[
            {
                "products": {"seller_id": [7]},
                "warehouses": {"warehouse_code": ["WH-SG-01"]},
                "quantity": {"kind": "integer", "min": 4, "max": 4},
            }
        ],
    )
    s.save_entity_profile(p)
    q = s.source_preview({})
    enqueue(s, w, "sync", preview=q["id"])
    enqueue(s, w, "bootstrap", customers=4, stock=999)
    assert {r["quantity_on_hand"] for r in s.data("inventory_levels")} == {4}
    assert all(
        r["gender"] in ["Female", "Male"]
        and "1980" <= r["date_of_birth"] <= "2000-12-31"
        for r in s.data("customers")
    )
    assert s.entity_profile() == p


def test_actor_role_scope_identity_and_import(platform):
    s, w, _ = platform
    initialize(s, w)
    p = profile(
        actors=[
            {
                "id": "contact-team",
                "roles": [role("SEL-02")],
                "entity": "sellers",
                "where": {"id": [7]},
                "attributes": {"department": {"kind": "constant", "value": "catalog"}},
            }
        ]
    )
    s.save_entity_profile(p)
    cfg = {
        "SEL-02": {
            "enabled": True,
            "count": 1,
            "params": {},
            "actor_pool": "contact-team",
            "schedule": {"start": "08:00:00", "end": "08:01:00"},
            "selection": {"sellers": {"id": [7]}},
        }
    }
    transfer = ConfigTransfer(s).preview(
        {"text": json.dumps({"format_version": 2, "config": cfg})}
    )
    assert transfer["config"]["SEL-02"]["selection"] == cfg["SEL-02"]["selection"]
    version = s.save_version({"config": cfg})["id"]
    plan = s.plan({"version": version, "start": "2026-11-01", "end": "2026-11-02"})
    enqueue(s, w, "run", plan=plan["id"])
    results = [r for r in s.db.list("action_results") if r.get("code") == "SEL-02"]
    assert len(results) == 2
    assert len({r["actor"]["id"] for r in results}) == 1
    assert all(r["actor"]["attributes"]["department"] == "catalog" for r in results)
    bad = copy.deepcopy(cfg)
    bad["GST-01"] = bad.pop("SEL-02")
    v = s.save_version({"config": bad})["id"]
    with pytest.raises(ValueError, match="actor"):
        s.plan({"version": v, "start": "2026-11-03", "end": "2026-11-03"})


def test_seller_actor_cannot_touch_another_shop(platform):
    s, w, _ = platform
    initialize(s, w)
    p = profile(
        actors=[
            {
                "id": "seller",
                "entity": "sellers",
                "roles": [role("SEL-02")],
                "where": {"id": [7]},
            }
        ]
    )
    s.save_entity_profile(p)
    # An explicit target cannot override actor ownership.
    from scripts.mock_platform.engine.domain import DomainEngine
    from scripts.mock_platform.infrastructure.storage import UnitOfWork

    with s.db.business.begin() as c, pytest.raises(NotEligible):
        DomainEngine(
            s.db,
            UnitOfWork(s.db, c),
            {
                "id": "foreign",
                "code": "SEL-02",
                "at": "2026-11-01T12:00:00",
                "entity_profile": p,
                "params": {"target": "999"},
                "actor_pool": "seller",
            },
            {},
        )


def test_session_duration_and_custom_payment_provider(platform):
    s, w, _ = platform
    s.save_entity_profile(
        profile(
            payment_methods=[{"method_name": "Cash On Delivery", "method_group": "COD"}]
        )
    )
    initialize(s, w)
    cfg = {
        "GST-WEB-01": {
            "enabled": True,
            "count": 1,
            "params": {},
            "schedule": {
                "start": "10:00:00",
                "end": "10:00:00",
                "duration_seconds": {"kind": "integer", "min": 900, "max": 900},
            },
        },
        "AUT-WEB-01": {"enabled": True, "mode": "all", "params": {}},
        "AUT-WEB-02": {"enabled": True, "mode": "all", "params": {}},
    }
    v = s.save_version({"config": cfg})["id"]
    plan = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=plan["id"])
    session = s.data("sessions")[0]
    assert session["ended_at"] == "2026-11-01T10:15:00"
    command(s, w, "CUS-05", at="2026-11-02T11:00:00", method="Cash On Delivery")
    assert s.data("orders") and not s.data("payments")


def test_inventory_reference_and_selection(platform):
    s, w, _ = platform
    initialize(s, w)
    command(s, w, "WH-01", warehouse=1, quantity=3)
    imports = [
        r for r in s.data("inventory_movements") if r["reference_code"] != "INITIAL"
    ]
    assert len(imports) == 1 and imports[0]["reference_code"].startswith("MOV:")


def test_contextual_parameter_rules_apply_after_actor_selection(platform):
    s, w, _ = platform
    initialize(s, w)
    p = profile(
        actors=[
            {
                "id": "customers",
                "entity": "customers",
                "roles": [role("CUS-05")],
                "where": {},
                "attributes": {"segment": {"kind": "constant", "value": "loyal"}},
            }
        ]
    )
    s.save_entity_profile(p)
    cfg = {
        "CUS-05": {
            "enabled": True,
            "count": 1,
            "params": {"method": "COD", "shipping_fee": 25000},
            "actor_pool": "customers",
            "parameter_rules": [
                {
                    "when": {"actor.attributes.segment": ["loyal"]},
                    "params": {"shipping_fee": 0},
                }
            ],
        }
    }
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=p["id"])
    assert s.data("orders")[0]["shipping_fee"] == 0
    receipt = s.db.list("action_results")[0]
    assert receipt["resolved_params"]["shipping_fee"] == 0
    assert s.db.list("action_results")[0]["actor"]["entity"] == "customers"
    cfg["CUS-05"]["parameter_rules"][0]["params"] = {"quantity": 99}
    with pytest.raises(ValueError):
        s.save_version({"config": cfg})


def test_visitor_journey_uses_same_actor_and_relative_time(platform):
    s, w, _ = platform
    initialize(s, w)
    codes = [
        "GST-WEB-01",
        "GST-WEB-02",
        "GST-WEB-03",
        "GST-WEB-04",
        "GST-WEB-06",
        "GST-02",
    ]
    s.save_entity_profile(
        profile(
            actors=[
                {
                    "id": "visitors",
                    "entity": "virtual",
                    "count": 10,
                    "roles": list({role(k) for k in codes}),
                    "attributes": {"segment": {"kind": "constant", "value": "new"}},
                }
            ]
        )
    )
    cfg = {
        k: {"enabled": True, "count": 1, "actor_pool": "visitors", "params": {}}
        for k in codes
    }
    cfg["GST-WEB-01"]["schedule"] = {
        "start": "09:00:00",
        "end": "09:00:00",
        "duration_seconds": {"kind": "integer", "min": 900, "max": 900},
    }
    for k, seconds in zip(codes[1:], [60, 120, 180, 240, 300]):
        cfg[k]["schedule"] = {
            "offset_seconds": {"kind": "integer", "min": seconds, "max": seconds}
        }
    cfg["GST-02"]["params"] = {"checkout_mode": "linked", "method": "COD"}
    cfg["AUT-WEB-01"] = {"enabled": True, "mode": "all", "params": {}}
    cfg["AUT-WEB-02"] = {"enabled": True, "mode": "all", "params": {}}
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=p["id"])
    results = [r for r in s.db.list("action_results") if r["code"] in codes]
    assert all(r["status"] == "DONE" for r in results), results
    assert len({r["actor"]["id"] for r in results}) == 1
    assert s.data("orders")[0]["created_at"] == "2026-11-01T09:05:00"
    assert s.data("sessions")[0]["ended_at"] == "2026-11-01T09:15:00"


def test_auto_actor_group_does_not_stop_at_member_without_work(platform):
    s, w, _ = platform
    initialize(s, w)
    from scripts.mock_platform.infrastructure.storage import UnitOfWork

    with s.db.business.begin() as c:
        u = UnitOfWork(s.db, c)
        seller = dict(u.one("sellers", 7))
        seller["id"] = 8
        u.add("sellers", **seller)
    s.save_entity_profile(
        profile(
            actors=[{"id": "shops", "entity": "sellers", "roles": [role("ORD-01")]}]
        )
    )
    command(s, w, "CUS-05", method="COD")
    cfg = {
        "ORD-01": {"enabled": True, "mode": "all", "params": {}, "actor_pool": "shops"}
    }
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=p["id"])
    assert s.data("orders")[0]["order_status"] == "Processing"
    results = [
        r
        for r in s.db.list("action_results")
        if r["code"] == "ORD-01" and r["status"] == "DONE"
    ]
    assert len(results) == 1 and results[0]["actor"]["entity_id"] == 7


def test_latest_examples_complete_linked_workflows_without_fixed_catalog_size(platform):
    from pathlib import Path

    from scripts.mock_platform.config.settings_transfer import SettingsTransfer
    from scripts.mock_platform.diagnostics.validation import BusinessValidator

    s, w, _ = platform
    root = Path(__file__).parents[3] / "docs/mock-design/examples"
    settings = json.loads((root / "settings/diverse-ecommerce.json").read_text())
    preview = SettingsTransfer(s).preview({"text": json.dumps(settings)})
    s.save_entity_profile(preview["entity_profile"])
    s.save_business_policy(preview["business_policy"])
    enqueue(s, w, "sync", preview=s.source_preview({})["id"])
    enqueue(s, w, "bootstrap", customers=30, stock=10)
    document = json.loads((root / "scenarios/upgraded-linked-2026.json").read_text())
    for entry in document["config"].values():
        if entry.get("mode") != "all":
            entry["count"] = 1 if entry.get("count") else 0
            entry["special"] = {
                d: 1 if n else 0 for d, n in entry.get("special", {}).items()
            }
    # This isolated catalog has one cart per audience/day; retaining one removal
    # would remove every cart. Keep the conversion branch populated explicitly.
    for code in ("GST-WEB-05", "CUS-WEB-05"):
        document["config"][code]["enabled"] = False
    version = ConfigTransfer(s).save({"text": json.dumps(document)})["id"]
    plan = s.plan({"version": version, "start": "2026-11-01", "end": "2026-11-20"})
    enqueue(s, w, "run", plan=plan["id"])
    report = BusinessValidator(s.db).report()
    assert report["ok"], report["errors"][:5]
    assert s.data("orders") and s.data("seller_payout_items") and s.data("refunds")
    assert any(r["refund_status"] == "Completed" for r in s.data("refunds"))
    assert any(r["campaign_id"] for r in s.data("sessions"))
    results = [r for r in s.db.list("action_results") if r["status"] == "DONE"]
    assert all(r.get("actor") for r in results)


def test_bootstrap_handles_catalog_beyond_sample_and_indexes_are_idempotent(platform):
    from sqlalchemy import event

    from scripts.mock_platform.infrastructure.indexes import migrate
    from scripts.mock_platform.infrastructure.storage import UnitOfWork

    s, w, _ = platform
    enqueue(s, w, "sync", preview=s.source_preview({})["id"])
    with s.db.business.begin() as c:
        u = UnitOfWork(s.db, c)
        base = dict(u.one("products", 123))
        for i in range(1000, 1250):
            u.add("products", **{**base, "id": i, "sku": f"test-{i}"})
    scanned = []

    def track(conn, cursor, statement, params, context, executemany):
        text = statement.upper()
        if (
            text.startswith("SELECT")
            and "FROM INVENTORY_LEVELS" in text
            and "WHERE" not in text
        ):
            scanned.append(text)

    event.listen(s.db.business, "before_cursor_execute", track)
    try:
        enqueue(s, w, "bootstrap", customers=0, stock=7)
    finally:
        event.remove(s.db.business, "before_cursor_execute", track)
    from sqlalchemy import func, select

    with s.db.business.connect() as c:
        assert (
            c.execute(
                select(func.count()).select_from(s.db.bm.tables["inventory_levels"])
            ).scalar()
            == 251
        )
    assert len(scanned) <= 2
    before = s.data("products")
    index = next(
        i
        for i in s.db.bm.tables["page_events"].indexes
        if i.name.startswith("ix_mock_")
    )
    with s.db.business.begin() as c:
        index.drop(c)
    assert index.name in migrate(s.db, apply=False)["indexes"]
    migrate(s.db, apply=True)
    assert migrate(s.db, apply=True)["indexes"] == []
    assert s.data("products") == before


def test_carrier_actor_collects_cod_for_its_delivered_order(platform):
    s, w, _ = platform
    initialize(s, w)
    command(s, w, "CUS-05", method="COD")
    command(s, w, "ORD-01")
    command(s, w, "DSP-01", warehouse=1, carrier=1)
    codes = ["CAR-01", "CAR-02", "CAR-03", "CAR-04"]
    s.save_entity_profile(
        profile(
            actors=[
                {
                    "id": "delivery",
                    "entity": "carriers",
                    "roles": list({role(k) for k in codes}),
                }
            ]
        )
    )
    cfg = {
        code: {
            "enabled": True,
            "mode": "all",
            "actor_pool": "delivery",
            "params": {"success_rate": 100} if code == "CAR-03" else {},
        }
        for code in codes
    }
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=p["id"])
    assert s.data("orders")[0]["order_status"] == "Completed"
    payments = s.data("payments")
    assert len(payments) == 1 and payments[0]["payment_status"] == "Success"
    receipt = next(
        r
        for r in s.db.list("action_results")
        if r["code"] == "CAR-04" and r["status"] == "DONE"
    )
    assert (
        receipt["actor"]["entity"] == "carriers" and receipt["actor"]["entity_id"] == 1
    )


def test_nullable_actor_filter_and_job_summary(platform):
    from fastapi.testclient import TestClient

    from scripts.mock_platform.interfaces.api import create_app

    s, w, _ = platform
    s.save_entity_profile(
        profile(
            customer_attributes={"gender": {"kind": "constant", "value": None}},
            actors=[
                {
                    "id": "missing-gender",
                    "entity": "customers",
                    "where": {"gender": [None]},
                    "roles": [role("CUS-01")],
                }
            ],
        )
    )
    initialize(s, w)
    cfg = {
        "CUS-01": {
            "enabled": True,
            "count": 1,
            "actor_pool": "missing-gender",
            "params": {"value": "Khách kiểm thử"},
        }
    }
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    j = enqueue(s, w, "run", plan=p["id"])
    client = TestClient(create_app(s))
    payload = client.get("/api/job/" + j["id"]).json()
    assert payload["result_summary"] == [
        {"code": "CUS-01", "status": "DONE", "count": 1}
    ]
    assert payload["results"][0]["actor"]["entity"] == "customers"
    saved = s.db.get("jobs", j["id"])
    s.db.put("jobs", j["id"], {**saved, "archived": True})
    assert client.get("/api/job/" + j["id"]).json()["backlog"] == []


def test_warehouse_selection_uses_address_reference_from_config(platform):
    s, w, _ = platform
    p = profile(
        actors=[{"id": "buyers", "entity": "customers", "roles": [role("CUS-05")]}]
    )
    p["locations"] = p["locations"][:1]
    second = {
        **p["warehouses"][0],
        "warehouse_code": "OTHER",
        "province": "Hà Nội",
        "city": "Hà Nội",
    }
    p["warehouses"].append(second)
    s.save_entity_profile(p)
    initialize(s, w)
    cfg = {
        "CUS-05": {
            "enabled": True,
            "count": 1,
            "params": {"method": "COD"},
            "actor_pool": "buyers",
            "selection": {"warehouses": {"province": {"ref": "address.province"}}},
        }
    }
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=p["id"])
    order = s.data("orders")[0]
    meta = s.db.get("runtime", "order:" + str(order["id"]))
    assert meta["warehouse"] == 1
    assert (
        next(i for i in s.data("inventory_levels") if i["warehouse_id"] == 2)[
            "quantity_reserved"
        ]
        == 0
    )


def test_job_resource_defaults_use_frozen_environment(platform):
    s, w, _ = platform
    s.save_entity_profile(
        profile(payment_methods=[{"method_name": "Provider A", "method_group": "COD"}])
    )
    initialize(s, w)
    v = s.save_version(
        {"config": {"CUS-05": {"enabled": True, "count": 1, "params": {}}}}
    )["id"]
    plan = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    s.save_entity_profile(
        profile(payment_methods=[{"method_name": "Provider B", "method_group": "COD"}])
    )
    enqueue(s, w, "run", plan=plan["id"])
    order = s.data("orders")[0]
    assert (
        s.db.get("runtime", "order:" + str(order["id"]))["method_name"] == "Provider A"
    )


def test_session_metadata_is_batched_not_one_query_per_candidate(platform):
    from sqlalchemy import event
    s,w,_=platform;initialize(s,w)
    cfg={'GST-WEB-01':{'enabled':True,'count':100,'params':{}},'GST-WEB-03':{'enabled':True,'count':1,'params':{}}}
    v=s.save_version({'config':cfg})['id'];p=s.plan({'version':v,'start':'2026-11-01','end':'2026-11-01'})
    queries=[]
    def track(conn,cursor,statement,params,context,executemany):
        if statement.lstrip().upper().startswith('SELECT') and "'runtime'" in repr(params):queries.append(statement)
    event.listen(s.db.control,'before_cursor_execute',track)
    try:enqueue(s,w,'run',plan=p['id'])
    finally:event.remove(s.db.control,'before_cursor_execute',track)
    assert len(queries)<10, len(queries)
    assert len(s.data('page_events'))==1
