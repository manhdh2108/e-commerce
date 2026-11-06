"""Stable selection of validated parameter bundles, independent of domain RNG."""

import copy
import hashlib
import random

ENGINE_VERSION = 2


class ParameterProfiles:
    @staticmethod
    def validate(variants):
        if not isinstance(variants, list) or not 1 <= len(variants) <= 100:
            raise ValueError("Profile phải có từ 1 đến 100 nhóm tham số.")
        names = set()
        for row in variants:
            if not isinstance(row, dict) or set(row) != {"name", "weight", "params"}:
                raise ValueError("Mỗi nhóm profile cần name, weight và params.")
            if (
                not isinstance(row["name"], str)
                or not row["name"].strip()
                or len(row["name"]) > 100
            ):
                raise ValueError("Tên nhóm profile phải có từ 1 đến 100 ký tự.")
            if row["name"] in names:
                raise ValueError("Tên nhóm profile không được trùng.")
            names.add(row["name"])
            if type(row["weight"]) is not int or not 1 <= row["weight"] <= 10000:
                raise ValueError("Trọng số profile phải là số nguyên từ 1 đến 10.000.")
            if not isinstance(row["params"], dict):
                raise ValueError("Tham số nhóm profile phải là object.")

    @staticmethod
    def resolve(entry, defaults, seed, action_id, index=0):
        params = copy.deepcopy(defaults)
        params.update(
            {k: v for k, v in entry.get("params", {}).items() if v not in (None, "")}
        )
        variants = entry.get("variants")
        if not variants:
            return params, None
        if entry.get("variant_mode") == "cycle":
            row = variants[index % len(variants)]
            params.update(
                {k: v for k, v in row["params"].items() if v not in (None, "")}
            )
            return params, row["name"]
        # No calls into DomainEngine.r: enabling a profile does not shift its draws.
        digest = hashlib.sha256(f"profiles:v1:{seed}:{action_id}".encode()).hexdigest()
        pick = random.Random(digest).randrange(sum(row["weight"] for row in variants))
        for row in variants:
            pick -= row["weight"]
            if pick < 0:
                params.update(
                    {k: v for k, v in row["params"].items() if v not in (None, "")}
                )
                return params, row["name"]
        raise AssertionError("Unreachable profile selection")
