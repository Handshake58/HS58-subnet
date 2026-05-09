"""
Registry client resilience. Validators must not crash when a registry is
unavailable. The fetch chain is:

    primary registry -> next registry -> ... -> local cache -> empty list

These tests mock requests.get and the cache file to verify each branch.
"""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from subnet58 import registry_client


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    cache = tmp_path / "registry_cache.json"
    monkeypatch.setattr(registry_client, "REGISTRY_CACHE_FILE", str(cache))
    return cache


def test_first_registry_success_writes_cache(isolated_cache):
    payload = {
        "providers": [
            {"id": "a", "probeUrl": "https://a.example", "name": "A", "protocol": "drain"},
            {"id": "b", "probeUrl": "https://b.example", "name": "B", "protocol": "mpp"},
        ]
    }

    with patch.object(registry_client.requests, "get", return_value=_FakeResponse(payload)):
        result = registry_client.fetch_providers(["https://r1"])

    assert len(result) == 2
    assert result[0]["id"] == "a"
    assert isolated_cache.exists()
    cached = json.loads(isolated_cache.read_text())
    assert cached == result


def test_failover_to_second_registry(isolated_cache):
    good_payload = {
        "providers": [
            {"id": "x", "probeUrl": "https://x.example", "name": "X", "protocol": "drain"},
        ]
    }

    call_log = []

    def fake_get(url, timeout):
        call_log.append(url)
        if url == "https://bad":
            raise RuntimeError("connection refused")
        return _FakeResponse(good_payload)

    with patch.object(registry_client.requests, "get", side_effect=fake_get):
        result = registry_client.fetch_providers(["https://bad", "https://good"])

    assert call_log == ["https://bad", "https://good"]
    assert len(result) == 1
    assert result[0]["id"] == "x"


def test_all_registries_fail_uses_cache(isolated_cache):
    cached_providers = [
        {"id": "cached", "probeUrl": "https://cached.example", "name": "C", "protocol": "drain"},
    ]
    isolated_cache.write_text(json.dumps(cached_providers))

    with patch.object(registry_client.requests, "get", side_effect=RuntimeError("down")):
        result = registry_client.fetch_providers(["https://r1", "https://r2"])

    assert result == cached_providers


def test_all_registries_fail_no_cache_returns_empty(isolated_cache):
    assert not isolated_cache.exists()

    with patch.object(registry_client.requests, "get", side_effect=RuntimeError("down")):
        result = registry_client.fetch_providers(["https://r1"])

    assert result == []


def test_field_mapping_handles_apiurl_alias(isolated_cache):
    payload = {
        "providers": [
            {"id": "legacy", "apiUrl": "https://legacy.example", "name": "Legacy"},
            {"id": "modern", "probeUrl": "https://modern.example", "name": "Modern", "protocol": "mpp"},
            {"id": "skipped", "name": "no url"},
        ]
    }

    with patch.object(registry_client.requests, "get", return_value=_FakeResponse(payload)):
        result = registry_client.fetch_providers(["https://r1"])

    assert len(result) == 2
    by_id = {p["id"]: p for p in result}
    assert by_id["legacy"]["probeUrl"] == "https://legacy.example"
    assert by_id["legacy"]["protocol"] == "drain"
    assert by_id["modern"]["protocol"] == "mpp"


def test_miners_alias_in_payload(isolated_cache):
    payload = {
        "miners": [
            {"id": "m1", "probeUrl": "https://m1.example", "name": "M1", "protocol": "drain"},
        ]
    }

    with patch.object(registry_client.requests, "get", return_value=_FakeResponse(payload)):
        result = registry_client.fetch_providers(["https://r1"])

    assert len(result) == 1
    assert result[0]["id"] == "m1"


def test_send_probe_alert_swallows_errors():
    with patch.object(registry_client.requests, "post", side_effect=RuntimeError("boom")):
        registry_client.send_probe_alert(
            provider_id="abc",
            probe_url="https://abc.example",
            consensus_reachable=False,
        )


def test_send_probe_alert_includes_validator_secret(monkeypatch):
    monkeypatch.setenv("VALIDATOR_SECRET", "topsecret")

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers

    with patch.object(registry_client.requests, "post", side_effect=fake_post):
        registry_client.send_probe_alert(
            provider_id="pid",
            probe_url="https://p.example",
            consensus_reachable=False,
            marketplace_url="https://market.example",
        )

    assert captured["url"] == "https://market.example/api/validator/probe-alert"
    assert captured["headers"].get("x-validator-secret") == "topsecret"
    assert captured["json"]["providerId"] == "pid"
    assert captured["json"]["reachable"] is False
