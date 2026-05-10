"""
ProviderProbe protocol: the Synapse contract between validator and miner.
These tests pin the on-the-wire shape so a refactor cannot silently rename
fields or break deserialization.
"""

from subnet58.protocol import ProviderProbe


def test_default_request_is_empty():
    probe = ProviderProbe()
    assert probe.target_url == ""
    assert probe.probe_latency_ms is None
    assert probe.probe_status is None
    assert probe.probe_reachable is None


def test_validator_sets_target_url():
    probe = ProviderProbe(target_url="https://example.com/health")
    assert probe.target_url == "https://example.com/health"


def test_miner_can_fill_response_fields():
    probe = ProviderProbe(target_url="https://x.example")
    probe.probe_reachable = True
    probe.probe_status = 200
    probe.probe_latency_ms = 123

    assert probe.probe_reachable is True
    assert probe.probe_status == 200
    assert probe.probe_latency_ms == 123


def test_deserialize_returns_all_four_fields():
    probe = ProviderProbe(target_url="https://x.example")
    probe.probe_reachable = False
    probe.probe_status = 502
    probe.probe_latency_ms = 5000

    data = probe.deserialize()

    assert set(data.keys()) == {
        "target_url",
        "probe_latency_ms",
        "probe_status",
        "probe_reachable",
    }
    assert data["target_url"] == "https://x.example"
    assert data["probe_reachable"] is False
    assert data["probe_status"] == 502
    assert data["probe_latency_ms"] == 5000


def test_402_payment_required_is_a_valid_status():
    """MPP providers respond 402 when alive; the protocol must accept it."""
    probe = ProviderProbe(target_url="https://mpp.example/x402")
    probe.probe_reachable = True
    probe.probe_status = 402
    probe.probe_latency_ms = 50

    data = probe.deserialize()
    assert data["probe_status"] == 402
    assert data["probe_reachable"] is True
