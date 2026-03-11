# Handshake58 Subnet 58 - DRAIN Event Scanner
#
# Scans ChannelClaimed events from the DrainChannel contract on Polygon.
# Returns total claimed amounts per provider address over a rolling window.

import math
from collections import defaultdict

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

        Anti-gaming: uses sqrt-per-channel scoring so that many small channels
        from diverse consumers score higher than one large self-dealing channel.

        Returns dict of provider_address -> diversity-weighted score (float).
        """
        from_block = self._get_block_n_days_ago(CLAIMS_WINDOW_DAYS)
        to_block = self.w3.eth.block_number

        bt.logging.info(
            f"[DRAIN] Scanning ChannelClaimed events: blocks {from_block} to {to_block} "
            f"({CLAIMS_WINDOW_DAYS}d window, ~{to_block - from_block} blocks)"
        )

        # Phase 1: Aggregate raw amounts per (provider, channelId)
        channel_amounts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
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
                    channel_id = log["topics"][1].hex()
                    provider = "0x" + log["topics"][2].hex()[-40:]
                    provider = provider.lower()
                    amount = int(log["data"].hex(), 16) / (10 ** USDC_DECIMALS)

                    channel_amounts[provider][channel_id] += amount
                    total_events += 1

            except Exception as e:
                bt.logging.warning(
                    f"[DRAIN] Log query failed for blocks {chunk_start}-{chunk_end}: {e}"
                )

            chunk_start = chunk_end + 1

        # Phase 2: sqrt per channel, then sum — rewards consumer diversity
        claims: dict = {}
        for provider, channels in channel_amounts.items():
            claims[provider] = sum(math.sqrt(amt) for amt in channels.values())

        bt.logging.info(
            f"[DRAIN] Scan complete: {total_events} events, "
            f"{len(claims)} unique providers, "
            f"{sum(len(ch) for ch in channel_amounts.values())} unique channels"
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


    def get_max_claims_by_category(self, wallet_categories: dict) -> dict:
        """
        Get maximum claimed amount per category.

        Args:
            wallet_categories: dict of wallet_address (lowercase) -> category string

        Returns:
            dict of category -> max_claimed_usd
        """
        category_max: dict = {}
        for wallet, amount in self.claims_cache.items():
            cat = wallet_categories.get(wallet)
            if cat is None:
                continue  # skip non-miner wallets entirely
            if amount > category_max.get(cat, 0):
                category_max[cat] = amount
        return category_max
