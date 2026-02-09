# Handshake58 Subnet 58 - DRAIN Event Scanner
#
# Scans ChannelClaimed events from the DrainChannel contract on Polygon.
# Returns total claimed amounts per provider address over a rolling window.

import bittensor as bt
from web3 import Web3

from subnet58.config import (
    DRAIN_CHANNEL_ADDRESS,
    POLYGON_RPC_ENDPOINTS,
    USDC_DECIMALS,
    BLOCKS_PER_DAY,
    CLAIMS_WINDOW_DAYS,
    LOG_QUERY_CHUNK_SIZE,
)


# keccak256("ChannelClaimed(bytes32,address,uint256)")
CHANNEL_CLAIMED_TOPIC = Web3.keccak(text="ChannelClaimed(bytes32,address,uint256)")


class DrainScanner:
    """
    Scans Polygon for DRAIN ChannelClaimed events.
    
    Uses chunked log queries with multi-RPC fallback.
    Returns: dict of provider_address (lowercase) -> total_claimed_usd (float)
    """

    def __init__(self):
        self.w3 = self._connect_rpc()
        self.claims_cache: dict = {}

    def _connect_rpc(self) -> Web3:
        """Connect to the first available Polygon RPC."""
        for url in POLYGON_RPC_ENDPOINTS:
            if not url:
                continue
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
                if w3.is_connected():
                    bt.logging.info(f"[DRAIN] Connected to Polygon RPC: {url[:40]}...")
                    return w3
            except Exception as e:
                bt.logging.warning(f"[DRAIN] RPC failed ({url[:40]}...): {e}")
                continue
        raise Exception("[DRAIN] No Polygon RPC available. Set POLYGON_RPC_URL env var.")

    def _get_block_n_days_ago(self, days: int) -> int:
        """Estimate block number from N days ago."""
        current_block = self.w3.eth.block_number
        blocks_back = days * BLOCKS_PER_DAY
        return max(current_block - blocks_back, 0)

    def update_claims(self) -> dict:
        """
        Scan ChannelClaimed events from last N days.
        Returns dict of provider_address -> total_claimed_usd.
        """
        from_block = self._get_block_n_days_ago(CLAIMS_WINDOW_DAYS)
        to_block = self.w3.eth.block_number

        bt.logging.info(
            f"[DRAIN] Scanning ChannelClaimed events: blocks {from_block} to {to_block} "
            f"({CLAIMS_WINDOW_DAYS}d window, ~{to_block - from_block} blocks)"
        )

        claims: dict = {}
        chunk_start = from_block
        total_events = 0

        while chunk_start <= to_block:
            chunk_end = min(chunk_start + LOG_QUERY_CHUNK_SIZE - 1, to_block)

            try:
                logs = self.w3.eth.get_logs({
                    "address": Web3.to_checksum_address(DRAIN_CHANNEL_ADDRESS),
                    "topics": [CHANNEL_CLAIMED_TOPIC],
                    "fromBlock": chunk_start,
                    "toBlock": chunk_end,
                })

                for log in logs:
                    # topics[2] = provider address (indexed)
                    provider = "0x" + log["topics"][2].hex()[-40:]
                    provider = provider.lower()

                    # data = amount (uint256)
                    amount = int(log["data"].hex(), 16) / (10 ** USDC_DECIMALS)

                    claims[provider] = claims.get(provider, 0) + amount
                    total_events += 1

            except Exception as e:
                bt.logging.warning(
                    f"[DRAIN] Log query failed for blocks {chunk_start}-{chunk_end}: {e}"
                )

            chunk_start = chunk_end + 1

        bt.logging.info(
            f"[DRAIN] Scan complete: {total_events} events, "
            f"{len(claims)} unique providers"
        )

        self.claims_cache = claims
        return claims

    def get_claims(self, provider_address: str) -> float:
        """Get total claimed amount for a provider address."""
        return self.claims_cache.get(provider_address.lower(), 0)

    def get_max_claims(self) -> float:
        """Get the maximum claimed amount across all providers."""
        if not self.claims_cache:
            return 0
        return max(self.claims_cache.values(), default=0)
