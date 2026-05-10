"""
Consensus computation: validators collapse a list of miner probe responses
into a single consensus snapshot via majority vote on reachable / status
plus median latency. These tests verify the Yuma-relevant invariants:

1. Empty / all-None responses produce a None consensus, not a crash.
2. Majority vote wins for reachable and status.
3. Latency uses the median (resilient to outliers).
4. Latencies <= 0 are excluded from the median.
5. Both Synapse-like objects (attribute access) and dict responses are
   accepted via the _field helper.
"""

from types import SimpleNamespace

from neurons.validator import Validator


def _resp(reachable, status, latency):
    return {
        "probe_reachable": reachable,
        "probe_status": status,
        "probe_latency_ms": latency,
    }


def test_no_responses_returns_none():
    assert Validator._compute_consensus([]) is None


def test_all_none_responses_returns_none():
    assert Validator._compute_consensus([None, None, None]) is None


def test_responses_without_reachable_field_are_ignored():
    responses = [
        {"probe_reachable": None, "probe_status": 200, "probe_latency_ms": 100},
        {"probe_reachable": None, "probe_status": 500, "probe_latency_ms": 200},
    ]
    assert Validator._compute_consensus(responses) is None


def test_majority_vote_on_reachable():
    responses = [
        _resp(True, 200, 100),
        _resp(True, 200, 110),
        _resp(False, 502, 120),
    ]
    cons = Validator._compute_consensus(responses)
    assert cons is not None
    assert cons.reachable is True


def test_majority_vote_on_status():
    responses = [
        _resp(True, 200, 100),
        _resp(True, 200, 110),
        _resp(True, 503, 120),
    ]
    cons = Validator._compute_consensus(responses)
    assert cons.status == 200


def test_median_latency_is_used():
    responses = [
        _resp(True, 200, 100),
        _resp(True, 200, 200),
        _resp(True, 200, 50_000),
    ]
    cons = Validator._compute_consensus(responses)
    assert cons.median_latency_ms == 200, "median resists single outlier"


def test_zero_and_negative_latencies_are_excluded():
    responses = [
        _resp(True, 200, 0),
        _resp(True, 200, -5),
        _resp(True, 200, 100),
        _resp(True, 200, 200),
    ]
    cons = Validator._compute_consensus(responses)
    assert cons.median_latency_ms == 150


def test_no_valid_latencies_returns_zero():
    responses = [
        _resp(True, 200, 0),
        _resp(True, 200, -10),
    ]
    cons = Validator._compute_consensus(responses)
    assert cons is not None
    assert cons.median_latency_ms == 0


def test_synapse_like_objects_via_attribute_access():
    responses = [
        SimpleNamespace(probe_reachable=True, probe_status=200, probe_latency_ms=100),
        SimpleNamespace(probe_reachable=True, probe_status=200, probe_latency_ms=120),
    ]
    cons = Validator._compute_consensus(responses)
    assert cons.reachable is True
    assert cons.status == 200
    assert cons.median_latency_ms == 110


def test_mixed_dict_and_object_responses():
    responses = [
        SimpleNamespace(probe_reachable=True, probe_status=200, probe_latency_ms=100),
        _resp(True, 200, 200),
        SimpleNamespace(probe_reachable=False, probe_status=503, probe_latency_ms=300),
    ]
    cons = Validator._compute_consensus(responses)
    assert cons.reachable is True
    assert cons.status == 200
    assert cons.median_latency_ms == 200


def test_consensus_is_deterministic():
    responses = [
        _resp(True, 200, 100),
        _resp(True, 200, 200),
        _resp(False, 502, 300),
    ]

    snapshots = {
        (Validator._compute_consensus(responses).reachable,
         Validator._compute_consensus(responses).status,
         Validator._compute_consensus(responses).median_latency_ms)
        for _ in range(20)
    }

    assert len(snapshots) == 1, "_compute_consensus must be deterministic"
