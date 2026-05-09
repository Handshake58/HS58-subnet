"""
Active miner filtering ensures the validator only probes UIDs with a
reachable axon and never probes itself. This prevents wasted probe attempts
against validators (no axon) and against the validator's own UID.
"""

from types import SimpleNamespace

from neurons.validator import Validator


class _FakeAxon:
    def __init__(self, ip: str):
        self.ip = ip


class _FakeMetagraph:
    def __init__(self, axon_ips):
        self.axons = [_FakeAxon(ip) for ip in axon_ips]
        self.n = SimpleNamespace(item=lambda: len(self.axons))


def _validator(axon_ips, self_uid: int):
    return SimpleNamespace(
        metagraph=_FakeMetagraph(axon_ips),
        uid=self_uid,
    )


def test_excludes_unreachable_axons():
    v = _validator(
        axon_ips=["1.1.1.1", "0.0.0.0", "2.2.2.2", "0.0.0.0"],
        self_uid=99,
    )

    active = Validator._get_active_miner_uids(v)

    assert active == [0, 2]


def test_excludes_self_uid():
    v = _validator(
        axon_ips=["1.1.1.1", "2.2.2.2", "3.3.3.3"],
        self_uid=1,
    )

    active = Validator._get_active_miner_uids(v)

    assert 1 not in active
    assert active == [0, 2]


def test_no_active_miners_returns_empty():
    v = _validator(
        axon_ips=["0.0.0.0", "0.0.0.0", "0.0.0.0"],
        self_uid=5,
    )

    active = Validator._get_active_miner_uids(v)

    assert active == []


def test_all_active_except_self():
    v = _validator(
        axon_ips=["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4"],
        self_uid=2,
    )

    active = Validator._get_active_miner_uids(v)

    assert active == [0, 1, 3]
