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
    assert len(s.db.bm.tables) == 33
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
        s.save_version({"config": {"SYS-04": {"enabled": True, "count": 1}}})
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


def test_edit_saved_config_in_place_invalidates_old_preview(platform):
    from scripts.mock_platform.service import ConfigurationConflict

    s, _, _ = platform
    old_config = {
        "GST-01": {"enabled": True, "count": 1, "params": {"province": "Hà Nội"}}
    }
    id = s.save_version({"name": "Cấu hình A", "config": old_config})["id"]
    plan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    changed = {
        "GST-01": {"enabled": True, "count": 3, "params": {"province": "Hà Nội"}}
    }
    result = s.update_version(
        id, {"revision": 1, "name": "Cấu hình đã sửa", "config": changed}
    )
    assert result == {"id": id, "revision": 2, "changed": True}
    assert len(s.db.list("versions")) == 1
    assert s.db.get("versions", id)["config"] == changed
    assert s.db.get("version_history", f"{id}:1")["config"] == old_config
    assert s.db.get("plans", plan["id"])["config_snapshot"] == old_config
    with pytest.raises(ValueError, match="hết hiệu lực"):
        s.newjob("run", {"request_key": "old-plan", "plan": plan["id"]})
    with pytest.raises(ConfigurationConflict):
        s.update_version(id, {"revision": 1, "name": "Đè cũ", "config": old_config})
    with TestClient(create_app(s)) as client:
        assert (
            client.put(
                f"/api/versions/{id}",
                json={"revision": 1, "name": "Stale", "config": old_config},
            ).status_code
            == 409
        )
        assert (
            client.put(
                f"/api/versions/{id}",
                json={"revision": 2, "name": "Cấu hình đã sửa", "config": changed},
            ).json()["changed"]
            is False
        )
    new = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    assert new["total"] == 3
    assert new["version_revision"] == 2


def test_edit_saved_config_does_not_change_queued_job(platform):
    s, w, _ = platform
    original = {
        "GST-01": {"enabled": True, "count": 2, "params": {"province": "Hà Nội"}}
    }
    id = s.save_version({"name": "Chạy 2 khách", "config": original})["id"]
    plan = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    job = s.newjob("run", {"request_key": "queued-before-edit", "plan": plan["id"]})
    s.update_version(
        id,
        {
            "revision": 1,
            "name": "Nay 5 khách",
            "config": {
                "GST-01": {
                    "enabled": True,
                    "count": 5,
                    "params": {"province": "Hà Nội"},
                }
            },
        },
    )
    w.tick()
    assert s.db.get("jobs", job["id"])["status"] == "COMPLETE"
    assert len(s.data("customers")) == 2
    assert s.db.get("plans", plan["id"])["config_snapshot"] == original


def test_paused_job_resumes_with_original_config_after_edit(platform, monkeypatch):
    s, w, _ = platform
    cfg = {"GST-01": {"enabled": True, "count": 3, "params": {"province": "Hà Nội"}}}
    id = s.save_version({"name": "3 khách", "config": cfg})["id"]
    p = s.plan({"version": id, "start": "2026-11-01", "end": "2026-11-01"})
    j = s.newjob("run", {"request_key": "pause-edit", "plan": p["id"]})
    original = w.paused
    calls = 0

    def pause_after_one(_):
        nonlocal calls
        calls += 1
        return calls >= 3

    monkeypatch.setattr(w, "paused", pause_after_one)
    w.tick()
    assert s.db.get("jobs", j["id"])["status"] == "PAUSED"
    assert len(s.data("customers")) == 1
    s.update_version(
        id,
        {
            "revision": 1,
            "name": "9 khách",
            "config": {
                "GST-01": {
                    "enabled": True,
                    "count": 9,
                    "params": {"province": "Hà Nội"},
                }
            },
        },
    )
    monkeypatch.setattr(w, "paused", original)
    s.command(j["id"], "resume")
    w.tick()
    assert s.db.get("jobs", j["id"])["status"] == "COMPLETE"
    assert len(s.data("customers")) == 3


def test_concurrent_saved_config_updates_do_not_overwrite(platform):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from scripts.mock_platform.service import ConfigurationConflict

    s, _, _ = platform
    if s.db.control.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locking")
    id = s.save_version({"name": "Initial", "config": {}})["id"]
    gate = Barrier(2)

    def change(name):
        gate.wait()
        try:
            s.update_version(id, {"revision": 1, "name": name, "config": {}})
            return "saved"
        except ConfigurationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, ["Edit A", "Edit B"]))
    assert sorted(results) == ["conflict", "saved"]
    assert s.db.get("versions", id)["revision"] == 2


def test_dashboard_and_source_check_are_read_only(platform):
    from scripts.mock_platform.operations import DataOperations

    s, w, source = platform
    initialize(s, w)
    op = DataOperations(s)
    before = source.read_bytes()
    counts = s.summary()["counts"]
    check = op.check_source()
    assert check["new"] == 0 and check["skipped"] == 1
    assert check["last_sync"]["status"] == "COMPLETE"
    dashboard = op.dashboard()
    assert dashboard["on_hand"] == 10 and dashboard["reserved"] == 0
    assert dashboard["order_amount"] == 0 and dashboard["daily_orders"] == []
    assert source.read_bytes() == before
    assert s.summary()["counts"] == counts
    with TestClient(create_app(s)) as client:
        assert client.get("/api/dashboard").status_code == 200
        assert client.post("/api/source-check", json={}).json()["new"] == 0


def test_reset_all_requires_confirmation_and_restores_initial_workflow(platform):
    from scripts.mock_platform.operations import DataOperations

    s, w, source = platform
    initialize(s, w)
    cfg = {"GST-01": {"enabled": True, "count": 2, "params": {}}}
    version = s.save_version({"name": "Giữ cấu hình", "config": cfg})["id"]
    plan = s.plan({"version": version, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=plan["id"])
    before = source.read_bytes()
    settings = s.setup()
    op = DataOperations(s)
    preview = op.reset_preview()
    assert preview["total"] == sum(s.summary()["counts"].values())
    assert s.summary()["counts"]["products"] == 1
    with pytest.raises(ValueError, match="XOA TOAN BO"):
        s.newjob("reset", {"request_key": "bad-reset", "preview": preview["id"]})
    enqueue(s, w, "reset", preview=preview["id"], confirmation="XOA TOAN BO")
    assert all(n == 0 for n in s.summary()["counts"].values())
    assert s.summary()["next_day"] == settings["start_date"]
    assert s.summary()["last_day"] is None
    assert s.db.get("bootstrap", "done") is None
    assert s.db.get("runtime", "bootstrap_done") is None
    assert s.db.list("daily") == []
    assert s.setup() == settings
    assert s.db.get("versions", version)["config"] == cfg
    assert source.read_bytes() == before
    assert op.sync_status()["last_sync"] is None
    with pytest.raises(ValueError):
        s.newjob("run", {"request_key": "old-plan", "plan": plan["id"]})
    initialize(s, w)
    newplan = s.plan({"version": version, "start": "2026-11-01", "end": "2026-11-01"})
    enqueue(s, w, "run", plan=newplan["id"])
    assert s.summary()["counts"]["customers"] == 5


def test_reset_crash_after_target_commit_recovers_and_cancels_paused_jobs(
    platform, monkeypatch
):
    from scripts.mock_platform.operations import DataOperations

    s, w, source = platform
    initialize(s, w)
    old = s.newjob(
        "bootstrap", {"request_key": "paused-bootstrap", "customers": 1, "stock": 1}
    )
    s.db.put("jobs", old["id"], {**s.db.get("jobs", old["id"]), "status": "PAUSED"})
    preview = DataOperations(s).reset_preview()
    reset = s.newjob(
        "reset",
        {
            "request_key": "crash-reset",
            "preview": preview["id"],
            "confirmation": "XOA TOAN BO",
        },
    )
    original = w.finish

    def crash(key, manifest):
        raise RuntimeError("Control unavailable after business commit")

    monkeypatch.setattr(w, "finish", crash)
    w.tick()
    assert s.db.get("jobs", reset["id"])["status"] == "FAILED"
    assert all(n == 0 for n in s.summary()["counts"].values())
    assert s.db.get("bootstrap", "done") is True
    # A fresh worker recovers the durable reset manifest instead of applying it blindly.
    monkeypatch.setattr(w, "finish", original)
    s.command(reset["id"], "resume")
    Worker(s).tick()
    assert s.db.get("jobs", reset["id"])["status"] == "COMPLETE"
    assert s.db.get("jobs", old["id"])["status"] == "CANCELLED"
    assert s.db.get("bootstrap", "done") is None
    with pytest.raises(ValueError, match="chưa ở trạng thái"):
        s.command(old["id"], "resume")


def test_stale_reset_preview_and_running_job_are_blocked(platform):
    from scripts.mock_platform.operations import DataOperations

    s, w, _ = platform
    preview = DataOperations(s).reset_preview()
    initialize(s, w)
    with pytest.raises(ValueError, match="thay đổi"):
        s.newjob(
            "reset",
            {
                "request_key": "stale-reset",
                "preview": preview["id"],
                "confirmation": "XOA TOAN BO",
            },
        )
    job = s.newjob(
        "sync", {"request_key": "pending-sync", "preview": s.source_preview({})["id"]}
    )
    preview = DataOperations(s).reset_preview()
    with pytest.raises(ValueError, match="dang dở"):
        s.newjob(
            "reset",
            {
                "request_key": "blocked-reset",
                "preview": preview["id"],
                "confirmation": "XOA TOAN BO",
            },
        )
    assert s.db.get("jobs", job["id"])["status"] == "QUEUED"


def test_crawler_queue_uses_existing_cli_without_syncing(
    platform, monkeypatch, tmp_path
):
    from scripts.mock_platform.crawler import CrawlerService, CrawlerWorker

    s, w, source = platform
    crawler = CrawlerService(s)
    crawler.folder = tmp_path / "crawl-logs"
    before = s.summary()["counts"]
    job = crawler.start(
        {
            "request_key": "crawl-one",
            "category_ids": [8322],
            "delay_min": 4,
            "delay_max": 8,
        }
    )
    assert (
        crawler.start({"request_key": "crawl-one", "category_ids": []})["id"]
        == job["id"]
    )
    with pytest.raises(ValueError, match="Đã có"):
        crawler.start({"request_key": "crawl-two"})
    worker = CrawlerWorker(s)
    worker.crawler = crawler
    calls = []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            calls.append(args)
            kwargs["stdout"].write(
                b"crawl_run_id=12345678-1234-4234-8234-123456789abc\nDone.\n"
            )

        def poll(self):
            return 0

        def wait(self, **kwargs):
            return 0

    monkeypatch.setattr("scripts.mock_platform.crawler.subprocess.Popen", FakeProcess)
    assert worker.tick()
    result = s.db.get("crawl_jobs", job["id"])
    assert result["status"] == "COMPLETE"
    assert result["crawl_run_id"] == "12345678-1234-4234-8234-123456789abc"
    assert calls[0][2].endswith("scripts/crawl_tiki.py")
    assert "--db" in calls[0] and str(source) in calls[0]
    assert "--category-ids" in calls[0] and "8322" in calls[0]
    assert s.summary()["counts"] == before and not s.db.list("jobs")
    cancelled = crawler.start({"request_key": "crawl-cancel"})
    crawler.stop(cancelled["id"])
    worker.tick()
    assert s.db.get("crawl_jobs", cancelled["id"])["status"] == "CANCELLED"
    assert len(calls) == 1


def test_dashboard_money_and_reset_of_related_business_rows(platform):
    from scripts.mock_platform.operations import DataOperations

    s, w, _ = platform
    test_end_to_end_and_special_day(platform)
    op = DataOperations(s)
    dashboard = op.dashboard()
    assert dashboard["order_amount"] == dashboard["completed_amount"] == 300000
    assert dashboard["paid_amount"] == 300000
    assert dashboard["on_hand"] == 7
    assert dashboard["orders"] == [{"status": "Completed", "count": 3}]
    assert [r["orders"] for r in dashboard["daily_orders"]] == [1, 2]
    preview = op.reset_preview()
    enqueue(s, w, "reset", preview=preview["id"], confirmation="XOA TOAN BO")
    assert all(n == 0 for n in s.summary()["counts"].values())
    with pytest.raises(ValueError, match="đồng bộ sản phẩm"):
        s.newjob(
            "bootstrap",
            {"request_key": "bootstrap-before-sync", "customers": 1, "stock": 10},
        )


def test_reset_delete_failure_rolls_back_every_business_table(platform):
    from sqlalchemy import event
    from scripts.mock_platform.operations import DataOperations

    s, w, _ = platform
    initialize(s, w)
    counts = s.summary()["counts"]
    preview = DataOperations(s).reset_preview()
    job = s.newjob(
        "reset",
        {
            "request_key": "rollback-reset",
            "preview": preview["id"],
            "confirmation": "XOA TOAN BO",
        },
    )

    def fail_midway(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM products"):
            raise RuntimeError("Simulated failure during deletion")

    event.listen(s.db.business, "before_cursor_execute", fail_midway)
    try:
        w.tick()
    finally:
        event.remove(s.db.business, "before_cursor_execute", fail_midway)
    assert s.db.get("jobs", job["id"])["status"] == "FAILED"
    assert s.summary()["counts"] == counts
    assert s.db.get("bootstrap", "done") is True
    s.command(job["id"], "resume")
    w.tick()
    assert s.db.get("jobs", job["id"])["status"] == "COMPLETE"


def test_import_preview_save_roundtrip_and_no_business_effects(platform):
    import json
    from scripts.mock_platform.config_transfer import ConfigTransfer

    s, _, source = platform
    counts, before = s.summary()["counts"], source.read_bytes()
    config = {"GST-01": {"enabled": True, "count": 3, "params": {"province": "Hà Nội"}}}
    text = json.dumps(
        {
            "format": "mock-studio-config",
            "format_version": 1,
            "name": "File thử",
            "config": config,
        }
    )
    with TestClient(create_app(s)) as client:
        p = client.post("/api/config-imports/preview", json={"text": text})
        assert p.status_code == 200, p.text
        assert p.json()["summary"]["enabled"] == 1
        assert not s.db.list("versions")
        first = client.post("/api/config-imports", json={"text": text})
        assert first.status_code == 201
        second = client.post(
            "/api/config-imports", json={"text": text, "name": "Bản khác"}
        )
        assert second.status_code == 201 and first.json()["id"] != second.json()["id"]
        assert len(s.db.list("versions")) == 2
        raw = ConfigTransfer(s).preview({"text": json.dumps(config)})
        stored = s.db.get("versions", first.json()["id"])
        assert raw["config"] == stored["config"]
        blank = ConfigTransfer(s).preview(
            {
                "text": json.dumps(
                    {
                        "WH-01": {
                            "enabled": True,
                            "params": {"quantity": None, "warehouse": ""},
                        }
                    }
                )
            }
        )
        assert blank["config"]["WH-01"]["params"] == {}
        assert stored["name"] == "File thử"
        template = client.get("/api/config-template")
        assert (
            template.status_code == 200
            and "attachment;" in template.headers["content-disposition"]
        )
        assert (
            ConfigTransfer(s).preview({"text": template.text})["summary"]["enabled"]
            > 20
        )
    assert s.summary()["counts"] == counts and source.read_bytes() == before
    assert not s.db.list("jobs") and s.db.get("draft", "main") is None


def test_import_rejects_malformed_or_unsupported_config_without_saving(platform):
    import json

    s, _, _ = platform
    bad = [
        "[]",
        "{}",
        "{",
        '{"GST-01":{},"GST-01":{}}',
        '{"GST-01":{"enabled":true,"params":{},"count":NaN}}',
        json.dumps({"name": "x", "config": {}, "unexpected": True}),
        json.dumps({"format_version": 3, "config": {}}),
    ]
    for code, cfg in [
        ("MISSING", {}),
        ("GST-01", {"enabled": "false"}),
        ("GST-01", {"enabled": True, "count": -1}),
        ("GST-01", {"special": []}),
        ("GST-01", {"params": []}),
        ("GST-01", {"special": {"2026-02-30": 1}}),
        ("GST-01", {"special": {"20261101": 1}}),
        ("GST-01", {"extra": 1}),
        ("SYS-04", {"enabled": True}),
        ("PAY-01", {"params": {"success_rate": 101}}),
        ("CUS-05", {"params": {"quantity": 1.5}}),
        ("WH-01", {"params": {"quantity": "10"}}),
        ("GST-01", {"params": {"province": "Invalid"}}),
        ("GST-01", {"params": {"value": "unknown"}}),
        ("SEL-05", {"params": {"value": ["wrong"]}}),
        ("GST-01", {"mode": "all"}),
    ]:
        bad.append(json.dumps({code: cfg}))
    bad.append('{"PAY-01":{"params":{"success_rate":1e309}}}')
    bad.append(json.dumps({"WH-01": {"params": {"quantity": 10**1000}}}))
    with TestClient(create_app(s)) as client:
        for text in bad:
            response = client.post("/api/config-imports", json={"text": text})
            assert response.status_code == 400, (text, response.text)
        assert (
            client.post(
                "/api/config-imports", json={"text": " " * (2 * 1024 * 1024 + 1)}
            ).status_code
            == 400
        )
    assert not s.db.list("versions") and not s.db.list("jobs")


def test_realistic_calendar_template_fits_engine_and_monthly_plan_limit(platform):
    import json
    from scripts.mock_platform.scenario import RealisticScenario
    from scripts.mock_platform.config_transfer import ConfigTransfer

    s, _, _ = platform
    scenario = RealisticScenario()
    document = scenario.build()
    assert document == json.loads(ConfigTransfer.template_path().read_text())
    assert len(scenario.schedule()) == 365
    cfg = document["config"]
    assert cfg["CAR-03"]["params"]["success_rate"] == 100
    assert not cfg["PAY-02"]["enabled"] and not cfg["FIN-REC-01"]["enabled"]
    assert not cfg["WH-03"]["enabled"]  # avoid a second stock issue path
    assert not cfg["GST-WEB-06"]["enabled"]  # no fake purchase/session link
    assert cfg["PAY-01"]["mode"] == "all" and cfg["SYS-01"]["mode"] == "all"
    assert len({r["orders"] for r in scenario.schedule()}) > 10
    assert all(row["count_actions"] < 100000 for row in scenario.monthly_stats())
    imported = ConfigTransfer(s).save({"text": json.dumps(document)})
    plan = s.plan(
        {"version": imported["id"], "start": "2026-11-01", "end": "2026-11-30"}
    )
    assert plan["total"] == scenario.monthly_stats()[10]["count_actions"]
    expected = next(
        r["orders"] for r in scenario.schedule() if r["day"] == "2026-11-11"
    )
    day = next(d for d in plan["days"] if d["day"] == "2026-11-11")
    assert (
        sum(a["requested"] for a in day["actions"] if a["code"] in ["GST-02", "CUS-05"])
        == expected
        == 64
    )


def test_realistic_template_rehearsal_in_isolated_database(platform):
    import json
    from scripts.mock_platform.scenario import RealisticScenario
    from scripts.mock_platform.config_transfer import ConfigTransfer
    from scripts.mock_platform.validation import BusinessValidator

    s, w, _ = platform
    enqueue(s, w, "sync", preview=s.source_preview({})["id"])
    enqueue(s, w, "bootstrap", customers=100, stock=200)
    document = RealisticScenario().build()
    # Synthetic fixture has category 625 and begins in November; match these inputs explicitly.
    document["config"]["FIN-POL-01"]["params"]["category"] = 625
    document["config"]["FIN-POL-01"]["special"] = {"2026-11-01": 1}
    imported = ConfigTransfer(s).save({"text": json.dumps(document)})
    plan = s.plan(
        {"version": imported["id"], "start": "2026-11-01", "end": "2026-11-02"}
    )
    enqueue(s, w, "run", plan=plan["id"])
    days = [
        r
        for r in RealisticScenario().schedule()
        if r["day"] in ["2026-11-01", "2026-11-02"]
    ]
    assert s.summary()["counts"]["orders"] == sum(r["orders"] for r in days)
    assert BusinessValidator(s.db).report()["ok"]
    assert s.summary()["counts"]["seller_commission_rates"] == 1
    assert s.summary()["counts"]["seller_payouts"] == 0
    assert all(r["session_id"] is None for r in s.data("orders"))
    assert all(r["total_discount_amount"] == 0 for r in s.data("orders"))
    assert {r["order_status"] for r in s.data("orders")} <= {"Completed", "Pending"}
