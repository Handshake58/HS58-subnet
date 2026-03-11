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
import requests

from eth_account.messages import encode_defunct
from eth_account import Account

import subnet58
from subnet58.protocol import ProviderCheck
from subnet58.base.validator import BaseValidatorNeuron
from subnet58.validator.drain_scanner import DrainScanner
from subnet58.config import WEIGHT_CLAIMS, WEIGHT_AVAILABILITY, MARKETPLACE_URL, BURN_UID, BURN_FRACTION


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
        3. Fetch provider categories from marketplace
        4. Score each miner (per-category normalization)
        5. Apply Winner Takes All (only top scorer per category keeps weight)
        6. Update scores
        """
        bt.logging.info("Starting validation round...")

        # 1. Query all miners with ProviderCheck
        miner_uids = list(range(self.metagraph.n.item()))
        axons = [self.metagraph.axons[uid] for uid in miner_uids]

        bt.logging.info(f"Querying {len(axons)} miners...")
        responses = self.dendrite.query(
            axons=axons,
            synapse=ProviderCheck(),
            timeout=self.config.neuron.timeout,
        )

        miner_wallet_set = {
            self._get_field(r, "polygon_wallet").lower()
            for r in responses
            if self._get_field(r, "polygon_wallet")
        }

        # 2. Scan DRAIN events (7-day window)
        bt.logging.info("Scanning DRAIN ChannelClaimed events...")
        self.drain_scanner.update_claims()

        # 3. Fetch provider categories from marketplace
        wallet_categories = self._fetch_provider_categories(miner_wallet_set)
        category_max = self.drain_scanner.get_max_claims_by_category(wallet_categories)

        bt.logging.info(
            f"Categories: {len(category_max)} with claims, "
            f"wallets mapped: {len(wallet_categories)}"
        )
        for cat, mx in sorted(category_max.items(), key=lambda x: -x[1]):
            bt.logging.info(f"  {cat}: max=${mx:.2f}")

        # 4. Score each miner (per-category max)
        rewards = np.zeros(len(miner_uids), dtype=np.float32)
        miner_wallets = {}
        miner_categories = {}

        for i, (uid, response) in enumerate(zip(miner_uids, responses)):
            hotkey = self.metagraph.hotkeys[uid]
            wallet = self._get_field(response, "polygon_wallet")

            if wallet:
                wallet_lower = wallet.lower()
                miner_wallets[i] = wallet_lower
                cat = wallet_categories.get(wallet_lower, "llm")
                miner_categories[i] = cat
                cat_max = category_max.get(cat, 0) or 1
                score = self._score_miner(response, hotkey, cat_max)
            else:
                score = self._score_miner(response, hotkey, 1)

            rewards[i] = score

        # 5. Winner Takes All — only top scorer per category keeps weight
        category_top: dict = {}
        for i, uid in enumerate(miner_uids):
            if rewards[i] <= 0:
                continue
            cat = miner_categories.get(i, "llm")
            if cat not in category_top or rewards[i] > rewards[category_top[cat]]:
                category_top[cat] = i

        wta_rewards = np.zeros_like(rewards)
        for cat, top_idx in category_top.items():
            wta_rewards[top_idx] = rewards[top_idx]
            uid = miner_uids[top_idx]
            wallet = miner_wallets.get(top_idx, "?")
            claims = self.drain_scanner.get_claims(wallet) if wallet != "?" else 0
            bt.logging.info(
                f"  WTA winner [{cat}] UID {uid}: score={rewards[top_idx]:.4f} "
                f"(wallet={wallet[:10]}..., claims=${claims:.2f})"
            )

        # 6. Update scores: 90% burn, 10% split equally across WTA winners
        scored_count = np.count_nonzero(wta_rewards)
        bt.logging.info(
            f"Validation round complete: {scored_count} WTA winners "
            f"from {len(category_top)} categories, {len(miner_uids)} total miners"
        )

        self.update_scores_with_burn(wta_rewards, miner_uids)

    def update_scores_with_burn(self, wta_rewards: np.ndarray, miner_uids: list):
        """
        Set self.scores for the upcoming set_weights() call.

        Distributes weight as:
          - BURN_UID gets BURN_FRACTION (default 90%) of total weight.
          - Remaining weight (default 10%) is split equally across WTA winners.
          - All other UIDs get 0.

        Does not use an exponential moving average — scores are set fresh
        each round so that set_weights() always reflects the current round.
        """
        winner_idxs = [i for i, r in enumerate(wta_rewards) if r > 0]
        n_winners = len(winner_idxs)

        new_scores = np.zeros(len(self.scores), dtype=np.float32)

        if n_winners == 0:
            bt.logging.warning("No WTA winners this round — scores not updated.")
            return

        new_scores[BURN_UID] = BURN_FRACTION
        winner_weight = (1.0 - BURN_FRACTION) / n_winners
        for i in winner_idxs:
            uid = miner_uids[i]
            new_scores[uid] = winner_weight

        bt.logging.info(
            f"Scores set: UID {BURN_UID} (burn) = {BURN_FRACTION:.0%}, "
            f"{n_winners} winner(s) = {winner_weight:.4f} each"
        )
        self.scores = new_scores

    def _fetch_provider_categories(self, miner_wallet_set: set) -> dict:
        """
        Fetch provider wallet -> category mapping from marketplace API.
        Falls back to empty dict (all miners default to "llm") if unreachable.
        """
        try:
            resp = requests.get(
                f"{MARKETPLACE_URL}/api/mcp/providers?limit=200",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            categories = {}
            for p in data.get("providers", []):
                addr = p.get("providerAddress", "").lower()
                if addr and addr in miner_wallet_set:
                    categories[addr] = p.get("category", "llm")

            bt.logging.info(
                f"[Categories] Fetched {len(categories)} provider categories "
                f"from marketplace"
            )
            return categories
        except Exception as e:
            bt.logging.warning(
                f"[Categories] Failed to fetch from marketplace: {e} "
                f"(all miners default to 'llm')"
            )
            return {}

    @staticmethod
    def _get_field(response, field: str, default=None):
        """Get a field from a response, handling both dict and Synapse objects."""
        if response is None:
            return default
        if isinstance(response, dict):
            return response.get(field, default)
        return getattr(response, field, default)

    def _score_miner(
        self, response, hotkey: str, max_claims: float
    ) -> float:
        """
        Score a single miner based on:
        - Availability (40%): Did they respond with a valid wallet proof?
        - DRAIN Claims (60%): Relative to top provider in same category
        """
        polygon_wallet = self._get_field(response, "polygon_wallet")
        if response is None or not polygon_wallet:
            return 0.0

        if not self._verify_ownership(response, hotkey):
            bt.logging.trace(f"Wallet ownership verification failed for {hotkey}")
            return 0.0

        score = WEIGHT_AVAILABILITY

        claims = self.drain_scanner.get_claims(polygon_wallet)
        if claims > 0 and max_claims > 0:
            claim_score = claims / max_claims
            score += WEIGHT_CLAIMS * claim_score

        return score

    def _verify_ownership(self, response, hotkey: str) -> bool:
        """
        Verify that the miner owns the claimed Polygon wallet.
        
        The miner signs "Bittensor Subnet 58 Miner: {hotkey}" with their
        Polygon private key. We recover the signer and check it matches
        the claimed wallet address.
        """
        wallet_proof = self._get_field(response, "wallet_proof")
        polygon_wallet = self._get_field(response, "polygon_wallet")

        if not wallet_proof or not polygon_wallet:
            return False

        try:
            message = f"Bittensor Subnet 58 Miner: {hotkey}"
            msg = encode_defunct(text=message)
            recovered = Account.recover_message(
                msg,
                signature=bytes.fromhex(
                    wallet_proof.replace("0x", "")
                ),
            )
            return recovered.lower() == polygon_wallet.lower()
        except Exception as e:
            bt.logging.trace(f"Wallet verification error: {e}")
            return False


# Entry point
if __name__ == "__main__":
    with Validator() as validator:
        while True:
            bt.logging.info(f"Validator running... {time.time()}")
            time.sleep(5)
