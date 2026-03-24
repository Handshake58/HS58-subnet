# Handshake58 Subnet 58 - Validator (Network Oracle)
#
# 1. Fetches provider list from marketplace registry
# 2. Sends ProviderProbe to all miners for random provider subset
# 3. Computes consensus (majority vote on reachable/status, median latency)
# 4. Scores miners by agreement with consensus (probe accuracy)
# 5. Sets weights via EMA-smoothed accuracy scores
from dotenv import load_dotenv
load_dotenv()

import sys
import time
import random
from collections import Counter
from statistics import median
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import bittensor as bt

import subnet58
from subnet58.protocol import ProviderProbe
from subnet58.base.validator import BaseValidatorNeuron
from subnet58.registry_client import fetch_providers, send_probe_alert
from subnet58.config import PROBES_PER_ROUND, MAX_LATENCY_DEVIATION


@dataclass
class Consensus:
    reachable: bool
    status: int
    median_latency_ms: int


class Validator(BaseValidatorNeuron):
    """
    Subnet 58 Validator — Network Oracle.

    Sends probe tasks to miners, evaluates their accuracy via consensus,
    and sets weights proportional to probe accuracy (EMA-smoothed).
    """

    def __init__(self, config=None):
        super(Validator, self).__init__(config=config)
        bt.logging.info("load_state()")
        self.load_state()
        bt.logging.info("Network Oracle validator ready.")

    async def forward(self):
        """
        One validation round: probe providers, score miners by consensus.
        """
        bt.logging.info("Starting validation round...")

        providers = fetch_providers()
        if not providers:
            bt.logging.warning("No providers from registry — skipping round.")
            return

        n_probes = min(PROBES_PER_ROUND, len(providers))
        targets = random.sample(providers, n_probes)
        bt.logging.info(
            f"Probing {n_probes}/{len(providers)} providers this round"
        )

        miner_uids = list(range(self.metagraph.n.item()))
        axons = [self.metagraph.axons[uid] for uid in miner_uids]

        # Accumulate accuracy per miner across all probes
        accuracy_sums = np.zeros(len(miner_uids), dtype=np.float32)
        probe_count = 0

        for target in targets:
            probe_url = target["probeUrl"]
            bt.logging.info(
                f"  Probe: {target['name']} ({target['protocol']}) -> {probe_url}"
            )

            responses = self.dendrite.query(
                axons=axons,
                synapse=ProviderProbe(target_url=probe_url),
                timeout=self.config.neuron.timeout,
            )

            consensus = self._compute_consensus(responses)
            if consensus is None:
                bt.logging.warning(f"  No valid responses for {probe_url}, skipping")
                continue

            bt.logging.info(
                f"  Consensus: reachable={consensus.reachable} "
                f"status={consensus.status} latency={consensus.median_latency_ms}ms"
            )

            if not consensus.reachable:
                send_probe_alert(
                    provider_id=target.get("id", ""),
                    probe_url=probe_url,
                    consensus_reachable=False,
                )

            for i, resp in enumerate(responses):
                accuracy_sums[i] += self._probe_accuracy(resp, consensus)

            probe_count += 1

        if probe_count == 0:
            bt.logging.warning("No successful probes this round.")
            return

        rewards = accuracy_sums / probe_count
        self.update_scores(rewards, miner_uids)

        nonzero = np.count_nonzero(self.scores)
        bt.logging.info(
            f"Round complete: {probe_count} probes, "
            f"{nonzero} miners with non-zero scores"
        )

    @staticmethod
    def _compute_consensus(responses) -> Optional[Consensus]:
        valid = [
            r for r in responses
            if r is not None and r.probe_reachable is not None
        ]
        if not valid:
            return None

        reachable_votes = [r.probe_reachable for r in valid]
        status_votes = [r.probe_status for r in valid]
        latencies = [
            r.probe_latency_ms for r in valid
            if r.probe_latency_ms is not None and r.probe_latency_ms > 0
        ]

        return Consensus(
            reachable=Counter(reachable_votes).most_common(1)[0][0],
            status=Counter(status_votes).most_common(1)[0][0],
            median_latency_ms=int(median(latencies)) if latencies else 0,
        )

    @staticmethod
    def _probe_accuracy(response, consensus: Consensus) -> float:
        """
        Score a single miner response against consensus.

        Weights: 40% reachable match, 30% status match, 30% latency closeness.
        """
        if response is None or response.probe_reachable is None:
            return 0.0

        reachable_match = float(response.probe_reachable == consensus.reachable)
        status_match = float(response.probe_status == consensus.status)

        lat = response.probe_latency_ms or 0
        if consensus.median_latency_ms > 0 and lat > 0:
            deviation = abs(lat - consensus.median_latency_ms)
            latency_score = max(0.0, 1.0 - deviation / MAX_LATENCY_DEVIATION)
        else:
            latency_score = reachable_match

        return 0.4 * reachable_match + 0.3 * status_match + 0.3 * latency_score


if __name__ == "__main__":
    with Validator() as validator:
        while True:
            if validator._update_exit_code is not None:
                bt.logging.info("Auto-update triggered, exiting for update.")
                sys.exit(validator._update_exit_code)
            bt.logging.info(f"Validator running... {time.time()}")
            time.sleep(60)
