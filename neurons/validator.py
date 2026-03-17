# Handshake58 Subnet 58 - Validator
#
# The validator:
# 1. Queries all miners with ProviderCheck Synapse
# 2. Verifies wallet ownership proofs (ECDSA recovery)
# 3. Scans DRAIN ChannelClaimed events on Polygon (7-day window)
# 4. Winner Takes All per category: verified miner with most claims wins
# 5. Sets weights on Bittensor (90% burn, 10% split equally across winners)

import sys
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
        3. Fetch marketplace registry (hotkey -> wallet + category)
        4. Verify ownership, registry membership, and wallet match
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

        # 2. Scan DRAIN events (3-day window)
        bt.logging.info("Scanning DRAIN ChannelClaimed events...")
        self.drain_scanner.update_claims()

        # 3. Fetch marketplace registry (hotkey -> {wallet, category})
        registry = self._fetch_provider_registry()

        if registry is None:
            bt.logging.warning(
                "Marketplace unreachable — keeping previous round scores."
            )
            return

        bt.logging.info(f"Marketplace registry: {len(registry)} registered miners")

        # 4. Verify ownership and collect claims per miner
        #    Three gates: ownership proof, hotkey in registry, wallet matches registration.
        miner_data = {}  # index i -> {uid, wallet, category, claims}

        for i, (uid, response) in enumerate(zip(miner_uids, responses)):
            hotkey = self.metagraph.hotkeys[uid]
            wallet = self._get_field(response, "polygon_wallet")

            if not wallet:
                continue
            if not self._verify_ownership(response, hotkey):
                bt.logging.trace(f"Wallet ownership verification failed for {hotkey}")
                continue

            if hotkey not in registry:
                continue
            reg = registry[hotkey]
            wallet_lower = wallet.lower()
            if wallet_lower != reg["wallet"]:
                bt.logging.trace(
                    f"Wallet mismatch for {hotkey[:10]}...: "
                    f"responded={wallet_lower[:10]}... registered={reg['wallet'][:10]}..."
                )
                continue
            cat = reg["category"]
            claims = self.drain_scanner.get_claims(wallet_lower)

            miner_data[i] = {
                "uid": uid,
                "wallet": wallet_lower,
                "category": cat,
                "claims": claims,
            }

        # 5. Winner Takes All per category (ties share the category's weight)
        category_winners = {}  # category -> [index, ...]

        for i, data in miner_data.items():
            cat = data["category"]
            claims = data["claims"]
            if cat not in category_winners:
                category_winners[cat] = [i]
            else:
                best = miner_data[category_winners[cat][0]]["claims"]
                if claims > best:
                    category_winners[cat] = [i]
                elif claims == best:
                    category_winners[cat].append(i)

        for cat in list(category_winners):
            if miner_data[category_winners[cat][0]]["claims"] == 0:
                bt.logging.info(f"  [{cat}] All miners have 0 claims — no winner")
                del category_winners[cat]

        n_winners = sum(len(indices) for indices in category_winners.values())
        for cat, indices in category_winners.items():
            for idx in indices:
                d = miner_data[idx]
                bt.logging.info(
                    f"  WTA winner [{cat}] UID {d['uid']}: "
                    f"wallet={d['wallet'][:10]}..., claims=${d['claims']:.2f}"
                    f"{' (tied)' if len(indices) > 1 else ''}"
                )

        # 6. Update scores: 90% burn, 10% split equally across categories,
        #    then equally among tied winners within each category.
        bt.logging.info(
            f"Validation round complete: {n_winners} WTA winners "
            f"from {len(category_winners)} categories, {len(miner_uids)} total miners"
        )
        self.update_scores_with_burn(category_winners, miner_data)

    def update_scores_with_burn(self, category_winners: dict, miner_data: dict):
        """
        Set self.scores for the upcoming set_weights() call.

        Weight is distributed per-category first, then split among tied
        winners within each category:
          - BURN_UID gets BURN_FRACTION (default 90%).
          - Remaining weight is split equally across categories.
          - Within each category, the share is split equally among winners.

        Example: 2 categories, one has a tie of 2 miners:
          burn=90%, each category gets 5%, tied miners each get 2.5%.
        """
        new_scores = np.zeros(len(self.scores), dtype=np.float32)
        n_categories = len(category_winners)

        if n_categories == 0:
            bt.logging.warning("No WTA winners this round — all weight to burn UID.")
            new_scores[BURN_UID] = 1.0
            self.scores = new_scores
            return

        new_scores[BURN_UID] = BURN_FRACTION
        category_weight = (1.0 - BURN_FRACTION) / n_categories

        for cat, indices in category_winners.items():
            per_miner = category_weight / len(indices)
            for i in indices:
                uid = miner_data[i]["uid"]
                new_scores[uid] = per_miner

        bt.logging.info(
            f"Scores set: UID {BURN_UID} (burn) = {BURN_FRACTION:.0%}, "
            f"{n_categories} categories, weight/category = {category_weight:.4f}"
        )
        self.scores = new_scores

    def _fetch_provider_registry(self) -> dict | None:
        """
        Fetch the marketplace provider registry.

        Returns:
            dict  – hotkey -> {"wallet": str, "category": str}  (may be empty)
            None  – marketplace was unreachable (caller should preserve previous scores)
        """
        try:
            resp = requests.get(
                f"{MARKETPLACE_URL}/api/validator/registry",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            registry = {}
            for p in data.get("miners", []):
                if p.get("tier", "") != "bittensor":
                    continue
                hk = p.get("hotkey", "")
                wallet = p.get("wallet", "").lower()
                if hk and wallet:
                    registry[hk] = {
                        "wallet": wallet,
                        "category": p.get("category", "llm"),
                    }

            bt.logging.info(
                f"[Registry] Fetched {len(registry)} registered providers "
                f"from marketplace"
            )
            return registry
        except Exception as e:
            bt.logging.warning(
                f"[Registry] Marketplace unreachable: {e}"
            )
            return None

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
            if validator._update_exit_code is not None:
                bt.logging.info("Auto-update triggered, exiting for update.")
                sys.exit(validator._update_exit_code)
            bt.logging.info(f"Validator running... {time.time()}")
            time.sleep(60)
