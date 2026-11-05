"""Settings import accepts only supported fields and has no persistence side effects."""

import copy
import json

from fastapi.testclient import TestClient

from scripts.mock_platform.api import create_app
from scripts.mock_platform.settings_transfer import SettingsTransfer
from scripts.mock_platform.storage import ROOT
from scripts.mock_platform.tests.test_platform import platform, initialize  # noqa: F401 — fixture


def test_settings_preview_fill_contract_and_no_writes(platform):
    s, w, source = platform
    initialize(s, w)
    policy, profile = s.business_policy(), s.entity_profile()
    before = (
        s.summary()["counts"],
        source.read_bytes(),
        s.db.list("versions"),
        s.db.list("jobs"),
    )
    text = SettingsTransfer.TEMPLATE.read_text()
    with TestClient(create_app(s)) as client:
        result = client.post("/api/settings-imports/preview", json={"text": text})
        assert result.status_code == 200, result.text
        p = result.json()
        assert p["business_policy"]["payout_hold_days"] == 10
        assert p["summary"] == {
            "surnames": 32,
            "given_names": 64,
            "name_combinations": 2048,
            "phone_prefixes": 30,
            "locations": 24,
            "provinces": 3,
            "warehouses": 6,
            "carriers": 5,
        }
        assert any("đã tạo dữ liệu nền" in w for w in p["warnings"])
        download = client.get("/api/settings-template")
        assert download.status_code == 200 and json.loads(download.text) == json.loads(
            text
        )
        # A settings file is intentionally rejected in the action-config tab.
        assert (
            client.post("/api/config-imports/preview", json={"text": text}).status_code
            == 400
        )
        assert s.business_policy() == policy and s.entity_profile() == profile
        assert before == (
            s.summary()["counts"],
            source.read_bytes(),
            s.db.list("versions"),
            s.db.list("jobs"),
        )
        # Existing save buttons can persist edited, validated form contents later.
        assert (
            client.put("/api/business-policy", json=p["business_policy"]).status_code
            == 200
        )
        assert (
            client.put("/api/entity-profile", json=p["entity_profile"]).status_code
            == 200
        )
        assert (
            s.business_policy() == p["business_policy"]
            and s.entity_profile() == p["entity_profile"]
        )
        assert s.summary()["counts"] == before[0] and source.read_bytes() == before[1]


def test_settings_policy_only_and_profile_only_preserve_other_section(platform):
    s, _, _ = platform
    policy = {
        "return_window_days": 5,
        "payout_hold_days": 8,
        "max_delivery_attempts": 2,
    }
    p = SettingsTransfer(s).preview({"text": json.dumps(policy)})
    assert (
        p["business_policy"] == policy
        and "entity_profile" not in p
        and not p["summary"]
    )
    profile = s.entity_profile()
    p = SettingsTransfer(s).preview(
        {
            "text": json.dumps(
                {
                    "format": "mock-studio-settings",
                    "format_version": 1,
                    "entity_profile": profile,
                }
            )
        }
    )
    assert p["entity_profile"] == profile and "business_policy" not in p


def test_settings_rejects_invalid_json_and_settings_without_changes(platform):
    s, _, _ = platform
    transfer = SettingsTransfer(s)
    valid = json.loads(transfer.TEMPLATE.read_text())
    bad = [
        "[]",
        "{}",
        "{",
        '{"return_window_days":7,"return_window_days":8}',
        json.dumps({"format": "mock-studio-config", "format_version": 2, "config": {}}),
        json.dumps({"format": "mock-studio-settings", "format_version": 1}),
        json.dumps(
            {"return_window_days": 7, "payout_hold_days": 7, "max_delivery_attempts": 3}
        ),
        json.dumps(
            {
                "return_window_days": True,
                "payout_hold_days": 8,
                "max_delivery_attempts": 3,
            }
        ),
        " " * (2 * 1024 * 1024 + 1),
    ]
    for key, value in [
        ("format_version", True),
        ("format_version", 2),
        ("extra", True),
        ("name", 7),
        ("business_policy", None),
    ]:
        document = copy.deepcopy(valid)
        document[key] = value
        bad.append(json.dumps(document))
    for edit in [
        lambda p: p["carriers"].append(p["carriers"][0]),
        lambda p: p["locations"][0].update(unknown="x"),
        lambda p: p.update(phone_prefixes=["abc"]),
        lambda p: p.update(warehouses=[]),
    ]:
        document = copy.deepcopy(valid)
        edit(document["entity_profile"])
        bad.append(json.dumps(document))
    bad.append(
        json.dumps(valid).replace(
            '"return_window_days": 7', '"return_window_days": NaN'
        )
    )
    original_policy = s.business_policy()
    original_profile = s.entity_profile()
    with TestClient(create_app(s)) as client:
        for text in bad:
            response = client.post("/api/settings-imports/preview", json={"text": text})
            assert response.status_code == 400, response.text
    assert (
        s.business_policy() == original_policy
        and s.entity_profile() == original_profile
    )


def test_all_relocated_scenario_downloads_still_validate(platform):
    s, _, _ = platform
    with TestClient(create_app(s)) as client:
        for path in ["/api/config-template", "/api/config-template-v2"]:
            response = client.get(path)
            assert response.status_code == 200, response.text
            assert (
                client.post(
                    "/api/config-imports/preview", json={"text": response.text}
                ).status_code
                == 200
            )
    for name in ["first-run-cod.json", "six-system-scenario.json"]:
        assert (ROOT / "docs/mock-design/examples/scenarios" / name).is_file()
