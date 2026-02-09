# Handshake58 Subnet 58 - Protocol
#
# ProviderCheck: Validator asks miner to prove wallet ownership and availability.
# 3 fields only. Validator reads DRAIN events directly from Polygon.

import typing
import bittensor as bt


class ProviderCheck(bt.Synapse):
    """
    Validator -> Miner request/response.

    The validator sends an empty ProviderCheck to the miner.
    The miner fills in its Polygon wallet, ownership proof, and API URL.
    The validator verifies the proof and scores based on DRAIN claims + availability.
    """

    # Response fields (miner fills these)
    polygon_wallet: typing.Optional[str] = None
    wallet_proof: typing.Optional[str] = None
    api_url: typing.Optional[str] = None

    def deserialize(self) -> typing.Dict[str, typing.Optional[str]]:
        return {
            "polygon_wallet": self.polygon_wallet,
            "wallet_proof": self.wallet_proof,
            "api_url": self.api_url,
        }
