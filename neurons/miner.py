# Handshake58 Subnet 58 - Miner (Neutral Monitor)
#
# Probes provider URLs on behalf of validators and reports
# reachability, HTTP status, and latency. No wallet, no registration.
from dotenv import load_dotenv
load_dotenv()

import time
import typing
import httpx
import bittensor as bt

import subnet58
from subnet58.protocol import ProviderProbe
from subnet58.base.miner import BaseMinerNeuron
from subnet58.config import PROBE_TIMEOUT_MS


class Miner(BaseMinerNeuron):
    """
    Subnet 58 Miner — Neutral Monitor.

    Receives ProviderProbe synapses from validators, performs HTTP GET
    on the target URL, and returns reachability + latency + status code.
    Scored by validators via consensus (agreement with majority).
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        self.http_client = httpx.AsyncClient(
            timeout=PROBE_TIMEOUT_MS / 1000,
            follow_redirects=True,
        )
        bt.logging.info(
            f"Neutral Monitor ready (timeout={PROBE_TIMEOUT_MS}ms, "
            f"hotkey={self.wallet.hotkey.ss58_address})"
        )

    async def forward(self, synapse: ProviderProbe) -> ProviderProbe:
        """Probe the target URL and fill response fields."""
        try:
            start_ns = time.perf_counter_ns()
            resp = await self.http_client.get(synapse.target_url)
            elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

            synapse.probe_reachable = True
            synapse.probe_status = resp.status_code
            synapse.probe_latency_ms = elapsed_ms
        except Exception:
            synapse.probe_reachable = False
            synapse.probe_status = 0
            synapse.probe_latency_ms = 0
        return synapse

    async def blacklist(
        self, synapse: ProviderProbe
    ) -> typing.Tuple[bool, str]:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            return True, "Missing dendrite or hotkey"

        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            return True, "Unrecognized hotkey"

        if self.config.blacklist.force_validator_permit:
            uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
            if not self.metagraph.validator_permit[uid]:
                return True, "Non-validator hotkey"

        return False, "Hotkey recognized"

    async def priority(self, synapse: ProviderProbe) -> float:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            return 0.0
        caller_uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        return float(self.metagraph.S[caller_uid])


if __name__ == "__main__":
    with Miner() as miner:
        while True:
            bt.logging.info(f"Miner running... {time.time()}")
            time.sleep(5)
