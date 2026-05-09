"""
Yuma-proof latency scoring: the latency component is a binary band check
(< MAX_LATENCY_DEVIATION -> 1.0, otherwise 0.0). This is geographically
deterministic: every validator computes the same score regardless of where
the miner or validator sits.

Verifies:
1. Latency strictly below threshold scores 1.0 on the latency component.
2. Latency at or above threshold scores 0.0 on the latency component.
3. Total accuracy uses the published 0.4 / 0.3 / 0.3 weighting.
4. Identical inputs always produce identical outputs (no hidden RNG).
"""

from neurons.validator import Validator, Consensus
from subnet58.config import MAX_LATENCY_DEVIATION


def _consensus(reachable=True, status=200, latency=100):
    return Consensus(
        reachable=reachable,
        status=status,
        median_latency_ms=latency,
    )


def _resp(reachable=True, status=200, latency=100):
    return {
        "probe_reachable": reachable,
        "probe_status": status,
        "probe_latency_ms": latency,
    }


def test_latency_below_threshold_scores_one():
    cons = _consensus()
    resp = _resp(latency=MAX_LATENCY_DEVIATION - 1)

    score = Validator._probe_accuracy(resp, cons)

    assert score == 1.0


def test_latency_at_threshold_scores_zero_band():
    cons = _consensus()
    resp = _resp(latency=MAX_LATENCY_DEVIATION)

    score = Validator._probe_accuracy(resp, cons)

    assert score == 0.4 + 0.3, "reachable + status only; latency band fails"


def test_latency_above_threshold_scores_zero_band():
    cons = _consensus()
    resp = _resp(latency=MAX_LATENCY_DEVIATION + 5_000)

    score = Validator._probe_accuracy(resp, cons)

    assert score == 0.4 + 0.3


def test_full_disagreement_scores_zero():
    cons = _consensus(reachable=True, status=200)
    resp = _resp(reachable=False, status=500, latency=MAX_LATENCY_DEVIATION + 1)

    score = Validator._probe_accuracy(resp, cons)

    assert score == 0.0


def test_weighting_uses_documented_split():
    cons = _consensus()
    only_reachable = _resp(reachable=True, status=999, latency=MAX_LATENCY_DEVIATION + 1)
    only_status = _resp(reachable=False, status=200, latency=MAX_LATENCY_DEVIATION + 1)
    only_latency = _resp(reachable=False, status=999, latency=10)

    assert Validator._probe_accuracy(only_reachable, cons) == 0.4
    assert Validator._probe_accuracy(only_status, cons) == 0.3
    assert Validator._probe_accuracy(only_latency, cons) == 0.3


def test_none_response_scores_zero():
    cons = _consensus()
    assert Validator._probe_accuracy(None, cons) == 0.0


def test_missing_reachable_field_scores_zero():
    cons = _consensus()
    resp = {"probe_reachable": None, "probe_status": 200, "probe_latency_ms": 100}
    assert Validator._probe_accuracy(resp, cons) == 0.0


def test_repeated_calls_are_deterministic():
    cons = _consensus()
    resp = _resp(latency=MAX_LATENCY_DEVIATION - 250)

    scores = {Validator._probe_accuracy(resp, cons) for _ in range(50)}

    assert len(scores) == 1, "_probe_accuracy must be deterministic"
