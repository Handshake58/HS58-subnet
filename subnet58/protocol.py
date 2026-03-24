# Handshake58 Subnet 58 - Protocol
#
# ProviderProbe: Validator sends a target URL, miner probes it and returns
# reachability, HTTP status, and latency. Protocol-agnostic (DRAIN + MPP).

import typing
import bittensor as bt


class ProviderProbe(bt.Synapse):
    """
    Validator -> Miner probe request/response.

    The validator sets target_url. The miner performs an HTTP GET,
    measures latency, and fills the response fields.
    Scoring is consensus-based: miners that agree with the majority score high.
    """

    # Request (validator sets)
    target_url: str = ""

    # Response (miner fills)
    probe_latency_ms: typing.Optional[int] = None
    probe_status: typing.Optional[int] = None
    probe_reachable: typing.Optional[bool] = None

    def deserialize(self) -> typing.Dict[str, typing.Any]:
        return {
            "target_url": self.target_url,
            "probe_latency_ms": self.probe_latency_ms,
            "probe_status": self.probe_status,
            "probe_reachable": self.probe_reachable,
        }
