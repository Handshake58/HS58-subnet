# Handshake58 Subnet 58 - Validator (Network Oracle)
#
# 1. Fetches provider list from marketplace registry
# 2. Deterministically selects providers via block-hash seed (Yuma-safe)
# 3. Sends ProviderProbe to all active miners
# 4. Computes consensus (majority vote on reachable/status)
# 5. Scores miners by agreement with consensus (probe accuracy)
# 6. Sets weights via EMA-smoothed accuracy scores
from dotenv import load_dotenv
load_dotenv()

import sys
import time
import random
import hashlib
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
from subnet58.config import PROBES_PER_ROUND, MAX_LATENCY_DEVIATION, TEMPO


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

    def _deterministic_sample(self, providers: list, n: int) -> list:
        """
        Select providers deterministically using the epoch's block hash.
        All validators on the same epoch pick the same providers,
        which is required for Yuma consensus weight agreement.

        Providers are sorted by probeUrl before sampling to ensure
        consistent ordering regardless of registry API response order.
        """
        sorted_providers = sorted(providers, key=lambda p: p.get("probeUrl", ""))

        epoch_block = (self.block // TEMPO) * TEMPO
        try:
            block_hash = self.subtensor.get_block_hash(epoch_block)
            seed = int(hashlib.sha256(block_hash.encode()).hexdigest(), 16)
        except Exception as e:
            bt.logging.warning(f"Could not get block hash, falling back to epoch number: {e}")
            seed = epoch_block

        rng = random.Random(seed)
        return rng.sample(sorted_providers, n)

    def _get_active_miner_uids(self) -> List[int]:
        """Filter UIDs to only active miners with a reachable axon."""
        return [
            uid for uid in range(self.metagraph.n.item())
            if self.metagraph.axons[uid].ip != "0.0.0.0"
            and uid != self.uid
        ]

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
        targets = self._deterministic_sample(providers, n_probes)
        bt.logging.info(
            f"Probing {n_probes}/{len(providers)} providers this round "
            f"(deterministic seed from epoch block {(self.block // TEMPO) * TEMPO})"
        )

        miner_uids = self._get_active_miner_uids()
        if not miner_uids:
            bt.logging.warning("No active miners found — skipping round.")
            return

        axons = [self.metagraph.axons[uid] for uid in miner_uids]
        bt.logging.info(f"Querying {len(miner_uids)} active miners")

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
    def _field(r, name):
        """Access a probe field from either a Synapse object or deserialized dict."""
        if isinstance(r, dict):
            return r.get(name)
        return getattr(r, name, None)

    @classmethod
    def _compute_consensus(cls, responses) -> Optional[Consensus]:
        valid = [
            r for r in responses
            if r is not None and cls._field(r, "probe_reachable") is not None
        ]
        if not valid:
            return None

        reachable_votes = [cls._field(r, "probe_reachable") for r in valid]
        status_votes = [cls._field(r, "probe_status") for r in valid]
        latencies = [
            cls._field(r, "probe_latency_ms") for r in valid
            if cls._field(r, "probe_latency_ms") is not None
            and cls._field(r, "probe_latency_ms") > 0
        ]

        return Consensus(
            reachable=Counter(reachable_votes).most_common(1)[0][0],
            status=Counter(status_votes).most_common(1)[0][0],
            median_latency_ms=int(median(latencies)) if latencies else 0,
        )

    @classmethod
    def _probe_accuracy(cls, response, consensus: Consensus) -> float:
        """
        Score a single miner response against consensus.

        Weights: 40% reachable match, 30% status match, 30% latency band.
        Latency uses a binary band check (< MAX_LATENCY_DEVIATION = 1.0, else 0.0)
        instead of median deviation — this is deterministic across all validators
        regardless of geographic location.
        """
        if response is None or cls._field(response, "probe_reachable") is None:
            return 0.0

        reachable_match = float(
            cls._field(response, "probe_reachable") == consensus.reachable
        )
        status_match = float(
            cls._field(response, "probe_status") == consensus.status
        )

        lat = cls._field(response, "probe_latency_ms") or 0
        if lat > 0:
            latency_score = 1.0 if lat < MAX_LATENCY_DEVIATION else 0.0
        else:
            latency_score = 0.0 if consensus.reachable else reachable_match

        return 0.4 * reachable_match + 0.3 * status_match + 0.3 * latency_score


if __name__ == "__main__":
    with Validator() as validator:
        while True:
            if validator._update_exit_code is not None:
                bt.logging.info("Auto-update triggered, exiting for update.")
                sys.exit(validator._update_exit_code)
            bt.logging.info(f"Validator running... {time.time()}")
            time.sleep(60)
