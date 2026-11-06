# ruff: noqa: F811
"""Regression tests for causal time, portable config and contextual selection."""

import json

import pytest

from scripts.mock_platform.application.service import ACTIONS
from scripts.mock_platform.config.config_transfer import ConfigTransfer
from scripts.mock_platform.config.configuration import ActionSchedule, Distribution
from scripts.mock_platform.config.settings_transfer import SettingsTransfer
from scripts.mock_platform.config.upgraded_scenario import UpgradedScenario
from scripts.mock_platform.diagnostics.validation import BusinessValidator
from scripts.mock_platform.engine.domain import DomainEngine
from scripts.mock_platform.engine.entities import EntityProfile
from scripts.mock_platform.infrastructure.storage import UnitOfWork
from scripts.mock_platform.resources import PROJECT_ROOT
from scripts.mock_platform.tests.test_platform import enqueue, platform  # noqa: F401

EXAMPLES = PROJECT_ROOT / "docs/mock-design/examples"


def setup_latest(s, w):
    settings = json.loads((EXAMPLES / "settings/diverse-ecommerce.json").read_text())
    p = SettingsTransfer(s).preview({"text": json.dumps(settings)})
    s.save_entity_profile(p["entity_profile"])
    s.save_business_policy(p["business_policy"])
    enqueue(s, w, "sync", preview=s.source_preview({})["id"])
    enqueue(s, w, "bootstrap", customers=4, stock=10)


def test_late_checkout_never_gets_earlier_payment_or_confirmation(platform):
    s, w, _ = platform
    setup_latest(s, w)
    doc = UpgradedScenario().build()
    keep = {
        "CUS-WEB-01",
        "CUS-WEB-03",
        "CUS-WEB-04",
        "CUS-WEB-06",
        "CUS-05",
        "PAY-01",
        "ORD-01",
    }
    for code, e in doc["config"].items():
        e["enabled"] = code in keep
        if code in keep:
            e["count"] = 1
            e["special"] = {}
            if code == "CUS-WEB-01":
                e["schedule"] = {
                    "start": "20:00:00",
                    "end": "20:00:00",
                    "duration_seconds": {"kind": "integer", "min": 3600, "max": 3600},
                }
            if code in ("CUS-WEB-03", "CUS-WEB-04", "CUS-WEB-06", "CUS-05"):
                offset = {
                    "CUS-WEB-03": 90,
                    "CUS-WEB-04": 180,
                    "CUS-WEB-06": 270,
                    "CUS-05": 360,
                }[code]
                e["schedule"] = {
                    "offset_seconds": {"kind": "integer", "min": offset, "max": offset}
                }
            if code == "CUS-05":
                e.pop("variants", None)
                e["params"]["method"] = "Momo"
            if code == "PAY-01":
                e["params"]["success_rate"] = 100
                e.pop("parameter_rules", None)
    id = ConfigTransfer(s).save({"text": json.dumps(doc)})["id"]
    p = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=p["id"])
    assert s.data("orders"), [
        (r["code"], r["status"], r.get("message")) for r in s.db.list("action_results")
    ]
    order = s.data("orders")[0]
    payment = s.data("payments")[0]
    assert order["created_at"] >= "2026-11-01T20:00:00"
    assert payment["transaction_time"] >= order["created_at"]
    assert order["updated_at"] >= payment["transaction_time"]
    assert BusinessValidator(s.db).report()["ok"]
    # Independent validator catches manually corrupted historical data.
    with s.db.business.begin() as c:
        c.execute(
            s.db.bm.tables["payments"]
            .update()
            .values(transaction_time="2026-11-01T10:00:00")
        )
    assert not BusinessValidator(s.db).report()["ok"]


def test_weighted_windows_and_patterns_are_validated_and_reproducible():
    spec = {
        "windows": [
            {"start": "07:00:00", "end": "08:00:00", "weight": 1},
            {"start": "20:00:00", "end": "21:00:00", "weight": 8},
        ]
    }
    ActionSchedule.validate(spec)
    times = [ActionSchedule.at("2026-01-01", spec, 42, str(i)) for i in range(300)]
    assert sum(t[11:13] == "20" for t in times) > 200
    assert times == [
        ActionSchedule.at("2026-01-01", spec, 42, str(i)) for i in range(300)
    ]
    for value in times:
        assert (
            "07:00:00" <= value[11:] <= "08:00:00"
            or "20:00:00" <= value[11:] <= "21:00:00"
        )
    p = {"kind": "pattern", "value": "09{digits:8}"}
    Distribution.validate(p)
    numbers = {Distribution.sample(p, 42, str(i)) for i in range(200)}
    assert len(numbers) == 200 and all(len(n) == 10 and n.isdigit() for n in numbers)
    with pytest.raises(ValueError):
        Distribution.validate({"kind": "pattern", "value": "{execute:4}"})
    with pytest.raises(ValueError):
        ActionSchedule.validate(
            {"windows": [{"start": "20:00:00", "end": "08:00:00", "weight": 1}]}
        )


def test_latest_import_preserves_execution_options_and_generator_source(platform):
    s, _, _ = platform
    original = UpgradedScenario().build()
    imported = ConfigTransfer(s).preview({"text": json.dumps(original)})["config"]
    assert imported["FIN-POL-01"]["variant_mode"] == "cycle"
    assert (
        imported["CUS-WEB-04"]["preferences"]
        == original["config"]["CUS-WEB-04"]["preferences"]
    )
    assert (
        imported["CUS-WEB-01"]["schedule"]
        == original["config"]["CUS-WEB-01"]["schedule"]
    )
    assert original == json.loads(
        (EXAMPLES / "scenarios/upgraded-linked-2026.json").read_text()
    )


def test_cycle_auto_exhaustion_covers_every_policy_tier(platform):
    s, w, _ = platform
    setup_latest(s, w)
    e = UpgradedScenario().build()["config"]["FIN-POL-01"]
    id = s.save_version({"config": {"FIN-POL-01": e}})["id"]
    p = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-02"})
    enqueue(s, w, "run", plan=p["id"])
    rates = s.data("seller_commission_rates")
    assert {r["seller_tier"] for r in rates} == {"Normal", "Preferred", "Mall"}
    assert len(rates) == 3


def test_returning_guest_keeps_recipient_identity(platform):
    s, w, _ = platform
    setup_latest(s, w)
    profile = s.entity_profile()
    pool = next(p for p in profile["actors"] if p["id"] == "visitors")
    pool["count"] = 1
    s.save_entity_profile(profile)
    for i in range(2):
        action = {
            "id": f"guest-identity-{i}",
            "code": "GST-02",
            "at": "2026-11-01T12:00:00",
            "seed": 42,
            "actor_pool": "visitors",
            "entity_profile": profile,
            "params": {
                **{f["key"]: f.get("default") for f in ACTIONS["GST-02"]["fields"]},
                "checkout_mode": "direct",
                "method": "COD",
                "product": 123,
            },
        }

        def apply(u, action=action):
            from scripts.mock_platform.infrastructure.storage import RuntimeState

            e = DomainEngine(s.db, u, action, RuntimeState(s.db))
            e.execute()
            return {"effects": e.effects}

        w.transact(f"guest-stability:{i}", apply)
    addresses = s.data("customer_addresses")
    assert len(addresses) == 2
    assert (
        len({(a["recipient_name"], a["phone"], a["address_detail"]) for a in addresses})
        == 1
    )


def test_preferences_require_a_viewed_product(platform):
    s, w, _ = platform
    setup_latest(s, w)
    # Exercise selection directly with persisted session context, not a matching implementation assertion.
    from scripts.mock_platform.tests.test_engine_v2 import command

    command(s, w, "CUS-WEB-01", target="1")
    command(s, w, "CUS-WEB-03", product=123)
    with s.db.business.begin() as c:
        u = UnitOfWork(s.db, c)
        original = u.one("products", 123)
        second = u.add(
            "products",
            **{k: v for k, v in original.items() if k != "id"}
            | {"id": 124, "sku": "second-sku"},
        )
        e = DomainEngine(
            s.db,
            u,
            {
                "id": "preferences-case",
                "code": "CUS-WEB-04",
                "at": "2026-11-01T12:30:00",
                "params": {},
                "preferences": {
                    "products": {
                        "source": "session_views",
                        "weight": 8,
                        "require": True,
                    }
                },
            },
            {},
        )
        e.choose("sessions")
        assert e.choose("products")["id"] == 123
        assert second["id"] == 124


def test_latest_quota_calendar_has_no_fixed_funnel_ratio():
    c = UpgradedScenario().build()["config"]
    ratios = set()
    for day in c["CUS-05"]["special"]:
        n = lambda code, day=day: c[code]["special"].get(day, c[code]["count"])
        orders = n("CUS-05") + n("GST-02")
        if orders:
            ratios.add(round((n("CUS-WEB-01") + n("GST-WEB-01")) / orders, 3))
    assert len(ratios) > 100
    p = json.loads((EXAMPLES / "settings/diverse-ecommerce.json").read_text())[
        "entity_profile"
    ]
    EntityProfile.validate(p)
    assert len({r["province"] for r in p["locations"]}) >= 4
    assert all(
        "mô phỏng" not in str(r).lower()
        for r in p["locations"] + p["warehouses"] + p["carriers"]
    )


def test_failed_refund_attempt_stays_pending_and_is_retried(platform):
    s, w, _ = platform
    setup_latest(s, w)
    from scripts.mock_platform.tests.test_engine_v2 import command

    command(s, w, "CUS-05", method="Momo")
    command(s, w, "PAY-01", success_rate=100)
    command(s, w, "CUS-07")
    assert s.data("refunds")[0]["refund_status"] == "Pending"
    command(s, w, "PAY-02", success_rate=0, retry_days=1)
    assert s.data("refunds")[0]["refund_status"] == "Pending"
    with pytest.raises(ValueError):
        command(s, w, "PAY-02", success_rate=100, at="2026-11-01T13:00:00")
    command(s, w, "PAY-02", success_rate=100, at="2026-11-03T12:00:00")
    assert s.data("refunds")[0]["refund_status"] == "Completed"
    attempts = s.db.get("runtime", "provider_attempt:refunds:1:PAY-02")
    assert attempts["attempts"] == 2


def test_staff_availability_is_enforced_before_writing(platform):
    s, w, _ = platform
    setup_latest(s, w)
    action = {
        "id": "off-hours",
        "code": "MKT-01",
        "at": "2026-11-01T03:00:00",
        "seed": 42,
        "actor_pool": "marketing-team-13",
        "entity_profile": s.entity_profile(),
        "params": {},
    }
    with s.db.business.begin() as c:
        e = DomainEngine(s.db, UnitOfWork(s.db, c), action, {})
        with pytest.raises(ValueError, match="khung giờ"):
            e.execute()
    assert not s.data("marketing_campaigns")


def test_configured_actor_sampling_changes_population_activity(platform):
    s, w, _ = platform
    setup_latest(s, w)
    with s.db.business.begin() as c:
        c.execute(s.db.bm.tables["customers"].update().values(membership_tier="Member"))
        c.execute(
            s.db.bm.tables["customers"]
            .update()
            .where(s.db.bm.tables["customers"].c.id == 1)
            .values(membership_tier="Gold")
        )
    profile = s.entity_profile()
    pool = next(p for p in profile["actors"] if p["id"] == "customers")
    pool["sampling"]["weights"] = {"Member": 1, "Gold": 1000}
    s.save_entity_profile(profile)
    version = s.save_version(
        {
            "config": {
                "CUS-WEB-01": {
                    "enabled": True,
                    "count": 50,
                    "params": {},
                    "actor_pool": "customers",
                }
            }
        }
    )["id"]
    plan = s.plan({"version": version, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=plan["id"])
    assert sum(r["customer_id"] == 1 for r in s.data("sessions")) > 45


def test_preference_probability_is_independent_of_catalog_size():
    import random
    from types import SimpleNamespace

    from scripts.mock_platform.engine.preferences import TargetPreferences

    engine = SimpleNamespace(
        a={"preferences": {"products": {"source": "session_interest", "weight": 9}}},
        selected_context={"sessions": {"id": 1}},
        getmeta=lambda *args: {"category_id": 1},
        r=random.Random(42),
    )
    rows = [{"id": i, "category_id": 1 if i == 0 else 2} for i in range(1001)]
    selector = TargetPreferences(engine)
    assert sum(selector.choose("products", rows)["id"] == 0 for _ in range(300)) > 240


def test_initial_customer_cohort_has_configured_history(platform):
    s, w, _ = platform
    setup_latest(s, w)
    customers = s.data("customers")
    assert len({r["registration_date"] for r in customers}) == 4
    assert all("2023-10-01" < r["registration_date"] < "2026-10-26" for r in customers)
    assert BusinessValidator(s.db).report()["ok"]
