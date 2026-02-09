# Handshake58 Subnet 58 - Validator
#
# The validator:
# 1. Queries all miners with ProviderCheck Synapse
# 2. Verifies wallet ownership proofs (ECDSA recovery)
# 3. Scans DRAIN ChannelClaimed events on Polygon (7-day window)
# 4. Scores: 60% DRAIN claims (relative) + 40% availability
# 5. Sets weights on Bittensor

import time
import numpy as np
import bittensor as bt

from eth_account.messages import encode_defunct
from eth_account import Account

import subnet58
from subnet58.protocol import ProviderCheck
from subnet58.base.validator import BaseValidatorNeuron
from subnet58.validator.drain_scanner import DrainScanner
from subnet58.config import WEIGHT_CLAIMS, WEIGHT_AVAILABILITY


class Validator(BaseValidatorNeuron):
    """
    Subnet 58 Validator.
    
    Scoring based on two trustless metrics:
    - DRAIN Claims (60%): Real USDC payments through DrainChannel contract
    - Availability (40%): Miner responds to Synapse with valid wallet proof
    """

    def __init__(self, config=None):
        super(Validator, self).__init__(config=config)

        bt.logging.info("load_state()")
        self.load_state()

        # Initialize DRAIN scanner
        bt.logging.info("Initializing DRAIN event scanner...")
        self.drain_scanner = DrainScanner()
        bt.logging.info("DRAIN scanner ready.")

    async def forward(self):
        """
        Validator forward pass:
        1. Query all miners
        2. Scan DRAIN events
        3. Score each miner
        4. Update scores
        """
        bt.logging.info("Starting validation round...")

        # 1. Query all miners with ProviderCheck
        miner_uids = list(range(self.metagraph.n.item()))
        axons = [self.metagraph.axons[uid] for uid in miner_uids]

        bt.logging.info(f"Querying {len(axons)} miners...")
        responses = await self.dendrite.query(
            axons=axons,
            synapse=ProviderCheck(),
            timeout=self.config.neuron.timeout,
        )

        # 2. Scan DRAIN events (7-day window)
        bt.logging.info("Scanning DRAIN ChannelClaimed events...")
        self.drain_scanner.update_claims()
        max_claims = self.drain_scanner.get_max_claims() or 1  # Avoid division by zero

        bt.logging.info(
            f"Max claims in window: ${max_claims:.2f} USDC "
            f"({len(self.drain_scanner.claims_cache)} providers with claims)"
        )

        # 3. Score each miner
        rewards = np.zeros(len(miner_uids), dtype=np.float32)

        for i, (uid, response) in enumerate(zip(miner_uids, responses)):
            hotkey = self.metagraph.hotkeys[uid]
            score = self._score_miner(response, hotkey, max_claims)
            rewards[i] = score

            if score > 0:
                wallet = getattr(response, "polygon_wallet", "?") or "?"
                claims = self.drain_scanner.get_claims(wallet) if wallet != "?" else 0
                bt.logging.info(
                    f"  UID {uid}: score={score:.4f} "
                    f"(wallet={wallet[:10]}..., claims=${claims:.2f})"
                )

        # 4. Update scores with exponential moving average
        scored_count = np.count_nonzero(rewards)
        bt.logging.info(
            f"Validation round complete: {scored_count}/{len(miner_uids)} miners scored"
        )

        self.update_scores(rewards, miner_uids)

    def _score_miner(
        self, response: ProviderCheck, hotkey: str, max_claims: float
    ) -> float:
        """
        Score a single miner based on:
        - Availability (40%): Did they respond with a valid wallet proof?
        - DRAIN Claims (60%): How much USDC was claimed through their wallet?
        """
        # No response or missing wallet = offline
        if response is None or not response.polygon_wallet:
            return 0.0

        # Verify wallet ownership (ECDSA signature)
        if not self._verify_ownership(response, hotkey):
            bt.logging.trace(f"Wallet ownership verification failed for {hotkey}")
            return 0.0

        # Base score: availability (40%)
        score = WEIGHT_AVAILABILITY

        # DRAIN Claims score (60%)
        claims = self.drain_scanner.get_claims(response.polygon_wallet)
        if claims > 0 and max_claims > 0:
            claim_score = claims / max_claims  # 0.0 - 1.0 (relative to top provider)
            score += WEIGHT_CLAIMS * claim_score

        return score

    def _verify_ownership(self, response: ProviderCheck, hotkey: str) -> bool:
        """
        Verify that the miner owns the claimed Polygon wallet.
        
        The miner signs "Bittensor Subnet 58 Miner: {hotkey}" with their
        Polygon private key. We recover the signer and check it matches
        the claimed wallet address.
        """
        if not response.wallet_proof or not response.polygon_wallet:
            return False

        try:
            message = f"Bittensor Subnet 58 Miner: {hotkey}"
            msg = encode_defunct(text=message)
            recovered = Account.recover_message(
                msg,
                signature=bytes.fromhex(
                    response.wallet_proof.replace("0x", "")
                ),
            )
            return recovered.lower() == response.polygon_wallet.lower()
        except Exception as e:
            bt.logging.trace(f"Wallet verification error: {e}")
            return False


# Entry point
if __name__ == "__main__":
    with Validator() as validator:
        while True:
            bt.logging.info(f"Validator running... {time.time()}")
            time.sleep(5)
