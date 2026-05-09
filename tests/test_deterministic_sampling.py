"""
Yuma-proof determinism: all validators on the same epoch must select the
exact same providers to probe. The Validator._deterministic_sample method
is the linchpin. These tests verify:

1. Same epoch block + same provider list -> identical sample (reproducibility)
2. Different epoch blocks -> different samples (with high probability)
3. Provider input ordering does not affect the sample (sorted by probeUrl)
4. n == len(providers) returns all providers (edge case)
5. Block-hash retrieval failure falls back to epoch number deterministically
"""

from types import SimpleNamespace

from neurons.validator import Validator
from subnet58.config import TEMPO


class _FakeSubtensor:
    """Minimal stub that returns a deterministic block hash per block number."""

    def __init__(self, fail: bool = False):
        self.fail = fail

    def get_block_hash(self, block: int) -> str:
        if self.fail:
            raise RuntimeError("block hash unavailable")
        return f"0x{block:064x}"


def _make_validator(block: int, fail_hash: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        block=block,
        subtensor=_FakeSubtensor(fail=fail_hash),
    )


def _providers(n: int):
    return [
        {"id": f"p{i}", "probeUrl": f"https://provider-{i:02d}.example/probe", "name": f"p{i}", "protocol": "drain"}
        for i in range(n)
    ]


def test_same_epoch_block_returns_identical_sample():
    providers = _providers(20)
    v = _make_validator(block=TEMPO * 5 + 17)

    s1 = Validator._deterministic_sample(v, providers, 5)
    s2 = Validator._deterministic_sample(v, providers, 5)

    assert s1 == s2, "Same epoch block must produce identical sample"


def test_different_epoch_blocks_produce_different_samples():
    providers = _providers(50)
    v_a = _make_validator(block=TEMPO * 1)
    v_b = _make_validator(block=TEMPO * 2)

    s_a = Validator._deterministic_sample(v_a, providers, 10)
    s_b = Validator._deterministic_sample(v_b, providers, 10)

    assert s_a != s_b, "Different epochs should produce different samples"


def test_input_order_does_not_affect_sample():
    providers = _providers(30)
    shuffled = list(reversed(providers))
    v = _make_validator(block=TEMPO * 7)

    s_sorted = Validator._deterministic_sample(v, providers, 8)
    s_reversed = Validator._deterministic_sample(v, shuffled, 8)

    assert s_sorted == s_reversed, "Sample must be invariant to input ordering"


def test_full_set_when_n_equals_provider_count():
    providers = _providers(5)
    v = _make_validator(block=TEMPO * 3)

    sample = Validator._deterministic_sample(v, providers, len(providers))

    assert len(sample) == len(providers)
    assert {p["id"] for p in sample} == {p["id"] for p in providers}


def test_block_hash_failure_falls_back_to_deterministic_seed():
    providers = _providers(15)
    v_fail = _make_validator(block=TEMPO * 4, fail_hash=True)

    s1 = Validator._deterministic_sample(v_fail, providers, 6)
    s2 = Validator._deterministic_sample(v_fail, providers, 6)

    assert s1 == s2, "Fallback path must still be deterministic"


def test_within_same_epoch_blocks_round_to_same_seed():
    providers = _providers(40)
    v_start = _make_validator(block=TEMPO * 9)
    v_mid = _make_validator(block=TEMPO * 9 + TEMPO // 2)
    v_end = _make_validator(block=TEMPO * 9 + TEMPO - 1)

    s_start = Validator._deterministic_sample(v_start, providers, 7)
    s_mid = Validator._deterministic_sample(v_mid, providers, 7)
    s_end = Validator._deterministic_sample(v_end, providers, 7)

    assert s_start == s_mid == s_end, (
        "All blocks within an epoch must round to the same seed"
    )
