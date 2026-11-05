import os
import uuid
import sqlite3
import pytest
from fastapi.testclient import TestClient
from scripts.mock_platform.storage import Database, UnitOfWork
from scripts.mock_platform.service import PlatformService
from scripts.mock_platform.worker import Worker
from scripts.mock_platform.api import create_app


@pytest.fixture
def platform(tmp_path):
    if os.getenv("MOCK_TEST_POSTGRES"):
        from sqlalchemy import create_engine

        admin = create_engine(
            os.environ["MOCK_TEST_POSTGRES"], isolation_level="AUTOCOMMIT"
        )
        suffix = uuid.uuid4().hex[:10]
        names = ["mock_test_control_" + suffix, "mock_test_business_" + suffix]
        with admin.connect() as c:
            for name in names:
                c.exec_driver_sql("CREATE DATABASE " + name)
        urls = [
            str(admin.url.set(database=name).render_as_string(hide_password=False))
            for name in names
        ]
        db = Database(*urls)
    else:
        db = Database(
            "sqlite:///" + str(tmp_path / "control.db"),
            "sqlite:///" + str(tmp_path / "business.db"),
        )
    db.start_control()
    source = tmp_path / "source.db"
    from scripts.crawl_tiki import open_database, save_page

    c = open_database(source)
    save_page(
        c,
        [
            {
                "id": 123,
                "sku": "00123",
                "name": "Sản phẩm thật",
                "seller_id": 7,
                "seller_product_id": 888,
                "price": 100000,
                "original_price": 120000,
                "is_visible": False,
            }
        ],
        8322,
        625,
    )
    c.close()
    s = PlatformService(db)
    s.prepare({"source": str(source), "start_date": "2026-11-01", "seed": 42})
    yield s, Worker(s), source
    db.control.dispose()
    db.business.dispose()
    if os.getenv("MOCK_TEST_POSTGRES"):
        with admin.connect() as c:
            for name in names:
                c.exec_driver_sql("DROP DATABASE " + name + " WITH (FORCE)")
        admin.dispose()


def enqueue(s, w, kind, **payload):
    job = s.newjob(kind, {"request_key": __import__("uuid").uuid4().hex, **payload})
    w.tick()
    result = s.db.get("jobs", job["id"])
    assert result["status"] == "COMPLETE", result
    return job


def initialize(s, w):
    preview = s.source_preview({})
    enqueue(s, w, "sync", preview=preview["id"])
    enqueue(s, w, "bootstrap", customers=3, stock=10)


def test_sync_append_only_and_no_side_effects(platform):
    s, w, source = platform
    before = s.summary()["counts"]
    p = s.source_preview({})
    assert s.summary()["counts"] == before
    enqueue(s, w, "sync", preview=p["id"])
    assert s.data("products")[0]["sku"] == "00123"
    assert s.data("products")[0]["is_active"] is True
    assert not s.data("orders") and not s.data("inventory_levels")
    c = sqlite3.connect(source)
    c.execute("UPDATE products SET price=50000")
    c.commit()
    c.close()
    p = s.source_preview({})
    assert p["new"] == 0 and p["skipped"] == 1
    enqueue(s, w, "sync", preview=p["id"])
    assert s.data("products")[0]["price"] == 100000
    assert len(s.db.bm.tables) == 27
    assert (
        "control_records"
        not in __import__("sqlalchemy").inspect(s.db.business).get_table_names()
    )


def test_end_to_end_and_special_day(platform):
    s, w, _ = platform
    initialize(s, w)
    config = {}
    for code in [
        "CUS-05",
        "ORD-01",
        "DSP-01",
        "CAR-01",
        "CAR-02",
        "CAR-03",
        "CAR-04",
        "CUS-09",
        "AUT-WH-04",
    ]:
        params = (
            {"method": "COD", "quantity": 1}
            if code == "CUS-05"
            else {"success_rate": 100}
            if code == "CAR-03"
            else {}
        )
        config[code] = {
            "enabled": True,
            "count": 1,
            "special": {"2026-11-02": 2},
            "params": params,
        }
    version = s.save_version({"config": config})["id"]
    with pytest.raises(ValueError, match="2026-11-01"):
        s.plan({"version": version, "start": "2026-11-02", "end": "2026-11-02"})
    p = s.plan({"version": version, "start": "2026-11-01", "end": "2026-11-02"})
    assert p["total"] == 27
    assert not s.data("orders")
    j = enqueue(s, w, "run", plan=p["id"])
    assert len(s.data("orders")) == 3
    assert all(o["order_status"] == "Completed" for o in s.data("orders"))
    assert len(s.data("payments")) == 3
    assert s.data("inventory_levels")[0]["quantity_on_hand"] == 7
    assert s.data("inventory_levels")[0]["quantity_reserved"] == 0
    assert len(s.data("inventory_daily_balance")) == 2
    assert s.summary()["last_day"] == "2026-11-02"
    before = s.data("orders")
    w.tick()
    assert s.data("orders") == before
    assert not s.db.get("jobs", j["id"])["rejected"]


def test_manifest_recovery_after_target_commit(platform, monkeypatch):
    s, w, _ = platform
    original = w.finish
    monkeypatch.setattr(
        w,
        "finish",
        lambda *_: (_ for _ in ()).throw(RuntimeError("crash after commit")),
    )
    with pytest.raises(RuntimeError):
        w.transact(
            "crash",
            lambda u: (
                u.add("channels", channel_name="Web", channel_type="Digital") and {}
            ),
        )
    assert len(s.data("channels")) == 1
    monkeypatch.setattr(w, "finish", original)
    w.transact(
        "crash",
        lambda _: (_ for _ in ()).throw(AssertionError("must not repeat insert")),
    )
    assert len(s.data("channels")) == 1
    assert s.db.get("receipts", "crash")["status"] == "DONE"


def test_stale_plan_and_api_readonly(platform):
    s, w, _ = platform
    initialize(s, w)
    with TestClient(create_app(s)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/catalog").status_code == 200
        assert (
            client.post(
                "/api/check", json={}, headers={"Origin": "https://example.com"}
            ).status_code
            == 403
        )
        assert (
            client.post("/api/versions", json={"config": {"NOT-REAL": {}}}).status_code
            == 400
        )
    v = s.save_version({"config": {}})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    w.transact("new-write", lambda u: u.add("channels", channel_name="Other") and {})
    with pytest.raises(ValueError, match="hết hiệu lực"):
        s.newjob("run", {"plan": p["id"], "request_key": "stale"})


def test_pause_and_duplicate_submission(platform):
    s, w, _ = platform
    initialize(s, w)
    v = s.save_version(
        {
            "config": {
                "GST-01": {
                    "enabled": True,
                    "count": 2,
                    "params": {"province": "Hà Nội"},
                }
            }
        }
    )["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    j = s.newjob("run", {"request_key": "same", "plan": p["id"]})
    assert s.newjob("run", {"request_key": "same", "plan": p["id"]})["id"] == j["id"]
    s.command(j["id"], "pause")
    w.tick()
    assert s.db.get("jobs", j["id"])["status"] == "PAUSED"
    assert s.summary()["last_day"] is None
    s.command(j["id"], "resume")
    w.tick()
    assert s.summary()["last_day"] == "2026-11-01"
    assert len(s.data("customers")) == 5


def test_wrong_seller_and_pending_job_blocks_new_work(platform):
    from scripts.mock_platform.domain import DomainEngine, NotEligible

    s, w, _ = platform
    initialize(s, w)
    with s.db.business.begin() as c:
        u = UnitOfWork(s.db, c)
        a = {
            "id": "wrong-owner",
            "code": "SEL-04",
            "at": "2026-11-01T08:00:00",
            "params": {"target": "123", "actor": "999", "value": "Wrong"},
        }
        with pytest.raises(NotEligible):
            DomainEngine(s.db, u, a, {}).execute()
    assert s.data("products")[0]["name"] == "Sản phẩm thật"
    v = s.save_version({"config": {}})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    j = s.newjob("run", {"request_key": "pause-me", "plan": p["id"]})
    s.command(j["id"], "pause")
    w.tick()
    with pytest.raises(ValueError, match="dang dở"):
        s.newjob("run", {"request_key": "new", "plan": p["id"]})


def test_auto_processes_input_and_conflicting_sku_skipped(platform):
    s, w, source = platform
    initialize(s, w)
    cfg = {
        "CUS-05": {
            "enabled": True,
            "count": 3,
            "params": {"method": "Momo", "quantity": 1},
        },
        "PAY-01": {
            "enabled": True,
            "count": 0,
            "mode": "all",
            "params": {"success_rate": 100},
        },
        "ORD-01": {"enabled": True, "count": 0, "mode": "all", "params": {}},
    }
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    assert p["total"] == 3 and p["days"][0]["automatic"] == 2
    enqueue(s, w, "run", plan=p["id"])
    assert len(s.data("payments")) == 3 and all(
        p["payment_status"] == "Success" for p in s.data("payments")
    )
    assert all(o["order_status"] == "Processing" for o in s.data("orders"))
    from scripts.crawl_tiki import open_database, save_page

    c = open_database(source)
    save_page(
        c,
        [
            {"id": 124, "sku": "SAME", "name": "A", "seller_id": 7, "price": 1000},
            {"id": 125, "sku": "SAME", "name": "B", "seller_id": 7, "price": 1000},
        ],
        8322,
        625,
    )
    c.close()
    p = s.source_preview({})
    assert p["new"] == 0 and len(p["errors"]) == 2


def test_calendar_ranges_and_backend_blocks_unavailable_actions(platform):
    from scripts.mock_platform.service import days

    s, _, _ = platform
    assert len(days("2024-01-01", "2024-12-31")) == 366
    assert len(days("2026-01-01", "2026-12-31")) == 365
    with pytest.raises(ValueError):
        s.save_version({"config": {"PAY-02": {"enabled": True, "count": 1}}})
    with pytest.raises(ValueError):
        s.save_version(
            {"config": {"CAT-04": {"enabled": True, "count": 1, "params": {}}}}
        )
    with pytest.raises(ValueError):
        s.save_version(
            {
                "config": {
                    "VIS-01": {"enabled": True, "count": 1},
                    "CUS-WEB-03": {"enabled": True, "count": 1},
                }
            }
        )


def test_marketing_analytics_and_source_metrics_independent(platform):
    s, w, _ = platform
    initialize(s, w)
    cfg = {
        code: {"enabled": True, "count": 1, "params": params}
        for code, params in {
            "MKT-01": {"value": "Campaign thử", "amount": 100000, "days": 7},
            "ADS-01": {"amount": 50000, "quantity": 10},
            "GST-WEB-01": {"channel": "Web", "traffic": "Organic", "device": "Mobile"},
            "CUS-WEB-01": {"channel": "Web", "traffic": "Direct", "device": "Desktop"},
            "GST-WEB-02": {"value": "Sách"},
            "CUS-WEB-03": {},
            "CUS-WEB-04": {"quantity": 1},
        }.items()
    }
    cfg["AUT-WEB-01"] = {"enabled": True, "mode": "all", "count": 0, "params": {}}
    cfg["AUT-WEB-02"] = {"enabled": True, "mode": "all", "count": 0, "params": {}}
    v = s.save_version({"config": cfg})["id"]
    p = s.plan({"version": v, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=p["id"])
    assert len(s.data("marketing_campaigns")) == 1 and len(s.data("ad_spend_logs")) == 1
    assert len(s.data("sessions")) == 2 and all(
        r["ended_at"] for r in s.data("sessions")
    )
    assert len(s.data("page_events")) == 3
    assert s.data("cart_items")[0]["cart_status"] == "Abandoned"
    assert s.data("products")[0]["quantity_sold"] is None
    from scripts.mock_platform.validation import BusinessValidator

    assert BusinessValidator(s.db).report()["ok"]


def test_initial_sale_status_is_explicit_not_source_visibility(platform):
    s, w, _ = platform
    preview = s.source_preview({"new_active": False})
    enqueue(s, w, "sync", preview=preview["id"])
    assert s.data("products")[0]["is_active"] is False
    again = s.source_preview({"new_active": True})
    assert again["new"] == 0
    enqueue(s, w, "sync", preview=again["id"])
    assert s.data("products")[0]["is_active"] is False
