"""Reject queued work when executable semantics changed after preview."""

import hashlib

from ..resources import PLATFORM_ROOT


class EngineContract:
    @staticmethod
    def snapshot():
        folder = PLATFORM_ROOT
        files = [
            "resources/actions.json",
            "resources/business_schema.json",
            "engine/domain.py",
            "engine/timing.py",
            "engine/preferences.py",
            "engine/outcomes.py",
            "application/worker.py",
            "application/service.py",
            "infrastructure/storage.py",
            "config/profiles.py",
            "config/configuration.py",
            "resources/defaults.json",
            "engine/actors.py",
            "engine/parameters.py",
            "infrastructure/indexes.py",
            "application/preflight.py",
            "application/operations.py",
            "engine/entities.py",
            "config/policies.py",
            "engine/purchase.py",
            "engine/benefits.py",
            "engine/aftersales.py",
            "engine/finance.py",
            "engine/selection.py",
            "diagnostics/validation.py",
            "application/contracts.py",
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
