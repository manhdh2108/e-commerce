"""A separate crawler queue; never imports or writes the OLTP engine."""

import fcntl
import math
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from ..application.service import PlatformService, stamp, uid
from ..resources import PROJECT_ROOT as ROOT


class CrawlerService:
    def __init__(self, service):
        self.s, self.db = service, service.db
        self.folder = ROOT / "data/mock-platform/crawler"

    @contextmanager
    def lock(self, name):
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / (name + ".lock")).open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError(
                    "Crawler đang được xử lý bởi tiến trình khác."
                ) from None
            try:
                yield handle
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def status(self):
        from scripts.crawl_tiki import CATEGORIES

        jobs = sorted(
            self.db.list("crawl_jobs"), key=lambda j: j["created_at"], reverse=True
        )
        return {
            "latest": jobs[0] if jobs else None,
            "jobs": jobs[:10],
            "categories": [{"id": k, "name": v} for k, v in CATEGORIES.items()],
            "source": self.s.setup().get("source"),
        }

    def start(self, payload):
        source = self.s.setup().get("source")
        if not source or not Path(source).is_file():
            raise ValueError("Chuẩn bị nguồn SQLite trong Thiết lập trước.")
        categories = payload.get("category_ids", [])
        if not isinstance(categories, list) or any(
            type(v) is not int or v <= 0 for v in categories
        ):
            raise ValueError("Danh mục phải là danh sách ID số nguyên dương.")
        low, high = payload.get("delay_min", 4), payload.get("delay_max", 8)
        if (
            any(
                type(v) not in (int, float) or not math.isfinite(v) for v in [low, high]
            )
            or not 0 <= low <= high <= 300
        ):
            raise ValueError(
                "Khoảng nghỉ phải thỏa 0 ≤ nhỏ nhất ≤ lớn nhất ≤ 300 giây."
            )
        key = payload.get("request_key")
        if not isinstance(key, str) or not key:
            raise ValueError("Thiếu khóa chống gửi lặp.")
        resume = payload.get("resume_run", "").strip()
        if resume:
            try:
                __import__("uuid").UUID(resume)
            except ValueError:
                raise ValueError("Mã tiếp tục crawler không hợp lệ.") from None
        with self.lock("queue"):
            jobs = self.db.list("crawl_jobs")
            old = next((j for j in jobs if j.get("request_key") == key), None)
            if old:
                return old
            if any(j["status"] in ["QUEUED", "RUNNING", "STOPPING"] for j in jobs):
                raise ValueError("Đã có lượt cào đang chạy hoặc đang chờ.")
            jid = uid()
            job = {
                "status": "QUEUED",
                "created_at": stamp(),
                "source": source,
                "category_ids": list(dict.fromkeys(categories)),
                "delay_min": low,
                "delay_max": high,
                "resume_run": resume,
                "request_key": key,
                "message": "Chờ worker cào dữ liệu",
                "log_tail": "",
                "stop": False,
            }
            self.db.put("crawl_jobs", jid, job)
            return {"id": jid, **job}

    def stop(self, jid):
        with self.lock("queue"):
            job = self.db.get("crawl_jobs", jid)
            if not job or job["status"] not in ["QUEUED", "RUNNING", "STOPPING"]:
                raise ValueError("Không có lượt cào đang hoạt động.")
            job["stop"] = True
            self.db.put("crawl_jobs", jid, job)
        return {"accepted": True}


class CrawlerWorker:
    def __init__(self, service=None):
        self.s = service or PlatformService()
        self.crawler = CrawlerService(self.s)
        self.db = self.s.db

    def arguments(self, job):
        args = [
            sys.executable,
            "-u",
            str(ROOT / "scripts/crawl_tiki.py"),
            "--db",
            job["source"],
            "--delay-min",
            str(job["delay_min"]),
            "--delay-max",
            str(job["delay_max"]),
        ]
        if job["category_ids"]:
            args += ["--category-ids", ",".join(map(str, job["category_ids"]))]
        if job.get("resume_run"):
            args += ["--resume-run", job["resume_run"]]
        return args

    def tick(self):
        with self.crawler.lock("worker") as worker_lock:
            jobs = sorted(
                [
                    j
                    for j in self.db.list("crawl_jobs")
                    if j["status"] in ["QUEUED", "RUNNING"]
                ],
                key=lambda j: j["created_at"],
            )
            if not jobs:
                return False
            job = jobs[0]
            jid = job.pop("id")
            if job["status"] == "RUNNING":
                # Never silently relaunch a crawl after a worker/process crash.
                job.update(
                    status="INTERRUPTED",
                    finished_at=stamp(),
                    message="Worker đã gián đoạn. Kiểm tra log và dùng mã tiếp tục nếu cần.",
                )
                self.db.put("crawl_jobs", jid, job)
                return True
            log_path = self.crawler.folder / (jid + ".log")
            if job.get("stop"):
                job.update(
                    status="CANCELLED",
                    finished_at=stamp(),
                    message="Đã hủy trước khi cào.",
                )
                self.db.put("crawl_jobs", jid, job)
                return True
            job.update(
                status="RUNNING",
                started_at=stamp(),
                log_path=str(log_path),
                message="Đang cào Tiki về SQLite; chưa đồng bộ OLTP.",
            )
            self.db.put("crawl_jobs", jid, job)
            process = None
            try:
                with log_path.open("ab", buffering=0) as output:
                    process = subprocess.Popen(
                        self.arguments(job),
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        cwd=ROOT,
                        pass_fds=(worker_lock.fileno(),),
                    )
                    while process.poll() is None:
                        latest = self.db.get("crawl_jobs", jid)
                        if latest.get("stop"):
                            process.terminate()
                            job["stop"] = True
                            break
                        self.update_log(jid, job, log_path)
                        time.sleep(1)
                    try:
                        code = process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        code = process.wait()
                job.update(
                    status="CANCELLED"
                    if job.get("stop")
                    else "COMPLETE"
                    if code == 0
                    else "FAILED",
                    finished_at=stamp(),
                    exit_code=code,
                    message="Đã dừng; các trang đã lưu vẫn ở SQLite."
                    if job.get("stop")
                    else "Cào hoàn tất. Sang Đồng bộ Tiki để kiểm tra sản phẩm mới."
                    if code == 0
                    else "Crawler có lỗi. Xem log; dữ liệu đã lưu vẫn được giữ.",
                )
            except BaseException:
                job.update(
                    status="INTERRUPTED",
                    finished_at=stamp(),
                    message="Crawler bị gián đoạn; xem log.",
                )
                raise
            finally:
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                self.update_log(jid, job, log_path)
            return True

    def update_log(self, jid, job, path):
        if path.exists():
            with path.open("rb") as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 8000))
                job["log_tail"] = log.read().decode("utf-8", errors="replace")
            import re

            match = re.search(r"crawl_run_id=([0-9a-f-]{36})", job["log_tail"])
            if match:
                job["crawl_run_id"] = match.group(1)
        # A separate stop record avoids overwriting a concurrent UI stop request.
        with self.crawler.lock("queue"):
            current = self.db.get("crawl_jobs", jid, {})
            job["stop"] = current.get("stop", False) or job.get("stop", False)
            self.db.put("crawl_jobs", jid, job)

    def loop(self):
        self.db.start_control()
        while True:
            try:
                if not self.tick():
                    time.sleep(1)
            except KeyboardInterrupt:
                break
            except Exception:
                __import__("traceback").print_exc()
                time.sleep(2)
