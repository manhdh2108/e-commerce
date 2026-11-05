"""Reject queued work when executable semantics changed after preview."""

import hashlib
from pathlib import Path


class EngineContract:
    @staticmethod
    def snapshot():
        folder = Path(__file__).parent
        files = [
            "actions.json",
            "business_schema.json",
            "domain.py",
            "worker.py",
            "service.py",
            "storage.py",
            "profiles.py",
            "entities.py",
            "policies.py",
            "purchase.py",
            "benefits.py",
            "aftersales.py",
            "finance.py",
            "selection.py",
            "validation.py",
            "contracts.py",
        ]
        digest = hashlib.sha256()
        for name in files:
            digest.update(name.encode())
            digest.update((folder / name).read_bytes())
        return {
            "engine_version": 2,
            "schema_version": 2,
            "fingerprint": digest.hexdigest(),
        }

    @classmethod
    def verify(cls, plan):
        if "config_snapshot" not in plan or plan.get("contract") != cls.snapshot():
            raise ValueError(
                "Code/hợp đồng engine đã đổi hoặc kế hoạch legacy thiếu bằng chứng. Lập kế hoạch mới; không resume ngầm job cũ bằng code mới."
            )
