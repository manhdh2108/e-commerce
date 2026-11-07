"""Resumable end-to-end driver: setup -> sync -> bootstrap -> import -> run chunks to END.

Runs inside WSL with the project venv. Safe to re-run: every step checks current state.
"""
import datetime as dt, json, sys, time, uuid, pathlib
import requests

B = "http://127.0.0.1:8765"
REPO = pathlib.Path("/mnt/d/PTIT/KÌ 1 năm 4/DATA WAREHOUSE/e-commerce")
EX = REPO / "docs/mock-design/examples"
SRC = str(REPO / "data/tiki_crawl_share.db")
SETTINGS, END, LIMIT = "medium-ecommerce.json", "2026-12-31", 95000
# Scenario schedule: (first simulated day, scenario file). A chunk never crosses a switch day.
# 2026-01-30: DW plan step 1.0 (docs/implementation/01_buoc-1.0_cau-hinh-mock-scd.md).
SCHEDULE = [("2026-01-01", "dw-lite-2026.json"), ("2026-01-30", "dw-scd-2026.json")]


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def call(method, path, body=None):
    # Up to ~1 hour of retries: the API can be briefly unreachable after the PC wakes up.
    for attempt in range(720):
        try:
            r = requests.request(method, B + path, json=body, timeout=600)
            break
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(5)
    else:
        raise SystemExit("API unreachable")
    if r.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:1500]}")
    return r.json()


def wait_job(jid, label, max_retries=30):
    """Wait for a job; auto-resume PAUSED, and FAILED/INTERRUPTED (e.g. DB connection
    dropped after the PC slept). The engine resumes from its receipts, so no action
    is applied twice."""
    last, retries = None, 0
    while True:
        j = call("GET", f"/api/job/{jid}")
        key = (j["status"], j.get("day"))
        if key != last:
            log(label, j["status"], "day", j.get("day"), "done", j.get("completed"), "rejected", j.get("rejected"), (j.get("message") or "")[:80])
            last = key
        if j["status"] == "PAUSED":
            call("POST", f"/api/job/{jid}/resume")
        elif j["status"] in ("FAILED", "INTERRUPTED") and retries < max_retries:
            retries += 1
            log(label, "auto-resume", retries, "after", j["status"])
            time.sleep(60)
            call("POST", f"/api/job/{jid}/resume")
        elif j["status"] not in ("QUEUED", "RUNNING", "PAUSING"):
            return j
        elif j["status"] == "RUNNING":
            retries = 0
        time.sleep(15)


def new_job(kind, payload):
    j = call("POST", f"/api/jobs/{kind}", {**payload, "request_key": str(uuid.uuid4())})
    return wait_job(j["id"], kind)


ov = call("GET", "/api/overview")
# Finish anything left over from an interrupted session.
for j in ov["jobs"]:
    if j["status"] in ("QUEUED", "RUNNING", "PAUSING", "PAUSED"):
        r = wait_job(j["id"], "leftover-" + j["kind"])
        if r["status"] != "COMPLETE":
            raise SystemExit(f"leftover job {j['id']} ended {r['status']}: {r.get('message')}")

ov = call("GET", "/api/overview")
if not ov["ready"]:
    call("POST", "/api/prepare", {"start_date": "2026-01-01", "seed": 42, "source": SRC})
    log("prepared")
if not call("GET", "/api/entity-profile").get("actors"):
    pv = call("POST", "/api/settings-imports/preview", {"text": (EX / "settings" / SETTINGS).read_text(encoding="utf-8")})
    call("PUT", "/api/entity-profile", pv["entity_profile"])
    call("PUT", "/api/business-policy", pv["business_policy"])
    log("settings saved")
def grant_dw_reader():
    """Quyền CHỈ ĐỌC cho ETL kho (dw/sql/00_init/002_source_grants.sql) — mất khi mock_oltp bị tạo lại."""
    try:
        import psycopg
        sql = (REPO / "dw/sql/00_init/002_source_grants.sql").read_text(encoding="utf-8")
        with psycopg.connect("postgresql://mock:local_mock_only@127.0.0.1:55432/mock_oltp", autocommit=True) as c:
            c.execute(sql)
        log("dw_reader grants applied")
    except Exception as exc:  # kho chưa khởi tạo (chưa có role) thì bỏ qua
        log("dw_reader grants skipped:", exc)


ov = call("GET", "/api/overview")
grant_dw_reader()
if not ov["counts"].get("products"):
    sp = call("POST", "/api/sync-previews", {"limit": 0})
    new_job("sync", {"preview": sp["id"]})
ov = call("GET", "/api/overview")
if not ov["counts"].get("customers"):
    new_job("bootstrap", {"customers": 10000, "stock": 0})
def version_for(day):
    """Saved config version for the scenario active on `day`, importing it if missing.
    Returns (version, last day this scenario applies)."""
    idx = max(i for i, (start, _) in enumerate(SCHEDULE) if start <= day)
    text = (EX / "scenarios" / SCHEDULE[idx][1]).read_text(encoding="utf-8")
    name = json.loads(text)["name"]
    version = next((v for v in call("GET", "/api/versions") if v["name"] == name), None)
    if not version:
        call("POST", "/api/config-imports", {"text": text})
        version = next(v for v in call("GET", "/api/versions") if v["name"] == name)
    until = END
    if idx + 1 < len(SCHEDULE):
        until = (dt.date.fromisoformat(SCHEDULE[idx + 1][0]) - dt.timedelta(days=1)).isoformat()
    return version, min(until, END)


def planned(cfg, day):
    return sum(c.get("special", {}).get(day, c.get("count", 0)) for c in cfg.values()
               if c.get("enabled") and c.get("mode") != "all")


while True:
    ov = call("GET", "/api/overview")
    start = ov["next_day"]
    if start > END:
        log("ALL DONE through", ov["last_day"])
        break
    version, until = version_for(start)
    cfg = version["config"]
    d, total, end = dt.date.fromisoformat(start), 0, None
    while d.isoformat() <= until:
        n = planned(cfg, d.isoformat())
        if end and total + n > LIMIT:
            break
        total, end = total + n, d.isoformat()
        d += dt.timedelta(days=1)
    plan = call("POST", "/api/plans", {"version": version["id"], "start": start, "end": end})
    log("chunk plan", start, "->", end, "planned", plan["total"], "version", version["name"])
    t0 = time.time()
    j = new_job("run", {"plan": plan["id"], "delay_ms": 0})
    log("chunk", start, "->", end, j["status"], "seconds", round(time.time() - t0))
    if j["status"] != "COMPLETE":
        raise SystemExit("stopped: " + j["status"] + " " + str(j.get("message")))
