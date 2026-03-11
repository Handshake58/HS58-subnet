# Handshake58 Subnet 58 - Validator
#
# The validator:
# 1. Queries all miners with ProviderCheck Synapse
# 2. Verifies wallet ownership proofs (ECDSA recovery)
# 3. Scans DRAIN ChannelClaimed events on Polygon (7-day window)
# 4. Winner Takes All per category: verified miner with most claims wins
# 5. Sets weights on Bittensor (90% burn, 10% split equally across winners)

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
from subnet58.config import MARKETPLACE_URL, BURN_UID, BURN_FRACTION


class Validator(BaseValidatorNeuron):
    """
    Subnet 58 Validator.

    Scoring: Winner Takes All per provider category.
    The verified miner with the most DRAIN USDC claims in their category wins.
    Winners split 10% of weight equally; 90% goes to the burn UID.
    """

    def __init__(self, config=None):
        super(Validator, self).__init__(config=config)

        bt.logging.info("load_state()")
        self.load_state()

        bt.logging.info("Initializing DRAIN event scanner...")
        self.drain_scanner = DrainScanner()
        bt.logging.info("DRAIN scanner ready.")

    async def forward(self):
        """
        Validator forward pass:
        1. Query all miners
        2. Scan DRAIN events
        3. Fetch provider categories (filtered to claimed miner wallets)
        4. Verify ownership and collect claims per miner
        5. Winner Takes All — verified miner with most claims wins per category
        6. Update scores (90% burn, 10% split equally across winners)
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

        # 2. Scan DRAIN events (7-day window)
        bt.logging.info("Scanning DRAIN ChannelClaimed events...")
        self.drain_scanner.update_claims()

        # Build wallet set from claimed wallets in responses (for category lookup filter)
        miner_wallet_set = {
            self._get_field(r, "polygon_wallet").lower()
            for r in responses
            if self._get_field(r, "polygon_wallet")
        }

        # 3. Fetch provider categories (filtered to claimed miner wallets only)
        wallet_categories = self._fetch_provider_categories(miner_wallet_set)
        bt.logging.info(f"Wallets mapped to categories: {len(wallet_categories)}")

        # 4. Verify ownership and collect claims per miner
        miner_data = {}  # index i -> {uid, wallet, category, claims}

        for i, (uid, response) in enumerate(zip(miner_uids, responses)):
            hotkey = self.metagraph.hotkeys[uid]
            wallet = self._get_field(response, "polygon_wallet")

            if not wallet:
                continue
            if not self._verify_ownership(response, hotkey):
                bt.logging.trace(f"Wallet ownership verification failed for {hotkey}")
                continue

            wallet_lower = wallet.lower()
            cat = wallet_categories.get(wallet_lower, "llm")
            claims = self.drain_scanner.get_claims(wallet_lower)

            miner_data[i] = {
                "uid": uid,
                "wallet": wallet_lower,
                "category": cat,
                "claims": claims,
            }

        # 5. Winner Takes All — verified miner with most claims wins per category
        category_winner = {}  # category -> index i

        for i, data in miner_data.items():
            cat = data["category"]
            if cat not in category_winner or data["claims"] > miner_data[category_winner[cat]]["claims"]:
                category_winner[cat] = i

        for cat, top_idx in category_winner.items():
            d = miner_data[top_idx]
            bt.logging.info(
                f"  WTA winner [{cat}] UID {d['uid']}: "
                f"wallet={d['wallet'][:10]}..., claims=${d['claims']:.2f}"
            )

        # 6. Update scores: 90% burn, 10% split equally across WTA winners
        winner_uids = [miner_data[i]["uid"] for i in category_winner.values()]
        bt.logging.info(
            f"Validation round complete: {len(winner_uids)} WTA winners "
            f"from {len(category_winner)} categories, {len(miner_uids)} total miners"
        )
        self.update_scores_with_burn(winner_uids)

    def update_scores_with_burn(self, winner_uids: list):
        """
        Set self.scores for the upcoming set_weights() call.

        Distributes weight as:
          - BURN_UID gets BURN_FRACTION (default 90%) of total weight.
          - Remaining weight (default 10%) is split equally across WTA winners.
          - All other UIDs get 0.

        Does not use an exponential moving average — scores are set fresh
        each round so that set_weights() always reflects the current round.
        """
        n_winners = len(winner_uids)
        new_scores = np.zeros(len(self.scores), dtype=np.float32)

        if n_winners == 0:
            bt.logging.warning("No WTA winners this round — scores not updated.")
            return

        new_scores[BURN_UID] = BURN_FRACTION
        winner_weight = (1.0 - BURN_FRACTION) / n_winners
        for uid in winner_uids:
            new_scores[uid] = winner_weight

        bt.logging.info(
            f"Scores set: UID {BURN_UID} (burn) = {BURN_FRACTION:.0%}, "
            f"{n_winners} winner(s) = {winner_weight:.4f} each"
        )
        self.scores = new_scores

    def _fetch_provider_categories(self, miner_wallet_set: set) -> dict:
        """
        Fetch provider wallet -> category mapping from marketplace API.
        Only returns entries for wallets present in miner_wallet_set.
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
