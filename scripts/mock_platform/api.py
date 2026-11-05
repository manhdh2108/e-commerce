import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .service import PlatformService, CATALOG


def create_app(service=None):
    s = service or PlatformService()

    @asynccontextmanager
    async def lifespan(app):
        s.db.start_control()
        yield

    app = FastAPI(title="Mock Studio", lifespan=lifespan)
    app.state.service = s

    @app.middleware("http")
    async def local_only(request, call_next):
        host = request.url.hostname
        origin = request.headers.get("origin")
        if host not in ["127.0.0.1", "localhost", "testserver"] or (
            origin and origin != f"{request.url.scheme}://{request.headers.get('host')}"
        ):
            return JSONResponse(
                {"error": "Chỉ chấp nhận truy cập local cùng origin."}, status_code=403
            )
        try:
            return await call_next(request)
        except (ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/overview")
    def overview():
        return s.summary()

    @app.get("/api/catalog")
    def catalog():
        return CATALOG

    @app.get("/api/versions")
    def versions():
        return sorted(
            s.db.list("versions"), key=lambda r: r["created_at"], reverse=True
        )

    @app.get("/api/draft")
    def draft_get():
        return s.db.get("draft", "main", {})

    @app.put("/api/draft")
    def draft_put(p: dict):
        return s.draft(p)

    @app.post("/api/versions")
    def version(p: dict):
        return s.save_version(p)

    @app.post("/api/prepare")
    def prepare(p: dict):
        return s.prepare(p)

    @app.post("/api/check")
    def check():
        with s.db.control.connect() as c:
            c.exec_driver_sql("SELECT 1")
        with s.db.business.connect() as c:
            c.exec_driver_sql("SELECT 1")
        return {
            "ok": True,
            "message": "Control DB và Business DB kết nối thành công, không ghi dữ liệu nghiệp vụ.",
        }

    @app.post("/api/sync-previews")
    def sync_preview(p: dict):
        return s.source_preview(p)

    @app.post("/api/plans")
    def plan(p: dict):
        return s.plan(p)

    @app.post("/api/jobs/{kind}", status_code=202)
    def jobs(kind: str, p: dict):
        if kind not in ["run", "sync", "bootstrap"]:
            raise ValueError("Loại job không hợp lệ.")
        if kind == "bootstrap":
            if not s.setup():
                raise ValueError("Chuẩn bị môi trường trước.")
            if s.db.get("bootstrap", "done"):
                raise ValueError("Dữ liệu nền đã tạo.")
            for k in ["customers", "stock"]:
                if type(p.get(k, 0)) is not int or not 0 <= p.get(k, 0) <= 10000:
                    raise ValueError("Số lượng nền phải từ 0 tới 10.000.")
        return s.newjob(kind, p)

    @app.post("/api/job/{id}/{command}")
    def command(id: str, command: str):
        if command not in ["pause", "resume"]:
            raise ValueError("Lệnh không hợp lệ.")
        return s.command(id, command)

    @app.get("/api/job/{id}")
    def job(id: str):
        j = s.db.get("jobs", id)
        if not j:
            raise ValueError("Job không tồn tại.")
        results = sorted(
            [r for r in s.db.list("action_results") if r.get("job") == id],
            key=lambda r: (r.get("at", ""), r.get("code", ""), r.get("order", 0)),
        )
        return {"id": id, **j, "results": results[-100:]}

    @app.get("/api/job/{id}/events")
    async def events(id: str, request: Request):
        async def stream():
            last = None
            while not await request.is_disconnected():
                data = s.db.get("jobs", id, {})
                encoded = json.dumps(data, ensure_ascii=False)
                if encoded != last:
                    yield f"data: {encoded}\n\n"
                    last = encoded
                else:
                    yield ": heartbeat\n\n"
                if data.get("status") in ["COMPLETE", "FAILED", "PAUSED"]:
                    break
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/data/{table}")
    def data(table: str, offset: int = 0):
        return s.data(table, max(offset, 0))

    @app.get("/api/validation")
    def validation():
        from .validation import BusinessValidator

        if not s.summary()["ready"]:
            raise ValueError(
                "Chưa có cấu trúc nghiệp vụ; hãy chuẩn bị môi trường trước."
            )
        return BusinessValidator(s.db).report()

    @app.get("/api/history")
    def history():
        return {
            "jobs": s.db.list("jobs"),
            "daily": s.db.list("daily"),
            "results": s.db.list("action_results")[-500:],
        }

    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    def index():
        return FileResponse(web / "index.html")

    return app
