# Handshake58 Subnet 58 - Miner
#
# The miner:
# 1. Signs a wallet ownership proof at startup (ECDSA with Polygon key)
# 2. Auto-registers on the Handshake58 marketplace (idempotent)
# 3. Responds to ProviderCheck Synapses with wallet + proof + API URL

import time
import typing
import requests
import bittensor as bt

from eth_account.messages import encode_defunct
from eth_account import Account

import subnet58
from subnet58.protocol import ProviderCheck
from subnet58.base.miner import BaseMinerNeuron
from subnet58.config import (
    MINER_POLYGON_WALLET,
    MINER_POLYGON_KEY,
    MINER_API_URL,
    MARKETPLACE_URL,
)


class Miner(BaseMinerNeuron):
    """
    Subnet 58 Miner.
    
    Proves ownership of a Polygon wallet and serves availability checks.
    Scoring is based on DRAIN ChannelClaimed events (read by validators)
    and this availability response.
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)

        # Validate required config
        if not MINER_POLYGON_WALLET:
            bt.logging.error("POLYGON_WALLET env var is required")
            exit(1)
        if not MINER_POLYGON_KEY:
            bt.logging.error("POLYGON_PRIVATE_KEY env var is required")
            exit(1)
        if not MINER_API_URL:
            bt.logging.error("API_URL env var is required")
            exit(1)

        self.polygon_wallet = MINER_POLYGON_WALLET
        self.polygon_private_key = MINER_POLYGON_KEY
        self.api_url = MINER_API_URL

        # Sign ownership proof once at startup
        bt.logging.info("Signing wallet ownership proof...")
        self.wallet_proof = self._sign_ownership()
        bt.logging.info(
            f"Wallet proof signed for {self.polygon_wallet} "
            f"(hotkey: {self.wallet.hotkey.ss58_address})"
        )

        # Auto-register on marketplace (non-blocking, non-critical)
        self._register_on_marketplace()

    def _sign_ownership(self) -> str:
        """
        ECDSA signature proving ownership of the Polygon wallet.
        
        Message format: "Bittensor Subnet 58 Miner: {hotkey_ss58}"
        Validator recovers the signer address and compares to claimed wallet.
        """
        message = f"Bittensor Subnet 58 Miner: {self.wallet.hotkey.ss58_address}"
        msg = encode_defunct(text=message)
        signed = Account.sign_message(msg, self.polygon_private_key)
        return signed.signature.hex()

    def _register_on_marketplace(self):
        """
        Auto-register on the Handshake58 marketplace.
        
        Uses sr25519 hotkey signature for marketplace verification.
        Idempotent via upsert on bittensorHotkey.
        """
        try:
            hotkey_ss58 = self.wallet.hotkey.ss58_address
            message = f"handshake58:{hotkey_ss58}:{self.api_url}"
            signature = self.wallet.hotkey.sign(message.encode()).hex()

            resp = requests.post(
                f"{MARKETPLACE_URL}/api/directory/providers",
                json={
                    "bittensorHotkey": hotkey_ss58,
                    "hotkeySignature": signature,
                    "apiUrl": self.api_url,
                    "providerAddress": self.polygon_wallet,
                    "name": f"Miner {self.uid}",
                },
                timeout=10,
            )
            bt.logging.info(
                f"Marketplace registration: {resp.status_code} - {resp.text[:100]}"
            )
        except Exception as e:
            bt.logging.warning(
                f"Marketplace registration failed (will retry on restart): {e}"
            )

    async def forward(self, synapse: ProviderCheck) -> ProviderCheck:
        """
        Handle ProviderCheck from validator.
        
        Simply returns our wallet, proof, and API URL.
        The validator verifies ownership and checks DRAIN claims.
        """
        synapse.polygon_wallet = self.polygon_wallet
        synapse.wallet_proof = self.wallet_proof
        synapse.api_url = self.api_url
        return synapse

    async def blacklist(
        self, synapse: ProviderCheck
    ) -> typing.Tuple[bool, str]:
        """Only allow registered entities to query this miner."""
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            return True, "Missing dendrite or hotkey"

        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            bt.logging.trace(
                f"Blacklisting unregistered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"

        # Only allow validators
        if self.config.blacklist.force_validator_permit:
            uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
            if not self.metagraph.validator_permit[uid]:
                return True, "Non-validator hotkey"

        return False, "Hotkey recognized"

    async def priority(self, synapse: ProviderCheck) -> float:
        """Prioritize by stake."""
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            return 0.0

        caller_uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        return float(self.metagraph.S[caller_uid])


# Entry point
if __name__ == "__main__":
    with Miner() as miner:
        while True:
            bt.logging.info(f"Miner running... {time.time()}")
            time.sleep(5)
