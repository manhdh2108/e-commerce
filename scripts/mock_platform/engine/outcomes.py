"""Retryable provider attempts; business obligations remain pending on failure."""

from datetime import datetime, timedelta


class ProviderAttempt:
    def __init__(self, engine):
        self.e = engine

    def succeed(self, table, row):
        e = self.e
        key = f"provider_attempt:{table}:{row['id']}:{e.code}"
        previous = e.getmeta(key, {})
        ok = e.r.random() * 100 < float(e.p.get("success_rate", 100))
        e.meta(
            key,
            {
                "attempts": previous.get("attempts", 0) + 1,
                "at": e.now,
                "status": "Success" if ok else "Failed",
            },
        )
        due = f"next_attempt:{table}:{row['id']}:{e.code}"
        e.meta(
            due,
            None
            if ok
            else (
                datetime.fromisoformat(e.now)
                + timedelta(days=int(e.p.get("retry_days", 1)))
            ).isoformat(timespec="seconds"),
        )
        return ok
