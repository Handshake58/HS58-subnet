# Handshake58 Subnet 58 - Configuration
#
# Constants for DRAIN Protocol integration and scoring.

import os

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
NETUID = 58

# ---------------------------------------------------------------------------
# DRAIN Protocol (Polygon Mainnet)
# ---------------------------------------------------------------------------
DRAIN_CHANNEL_ADDRESS = "0x0C2B3aA1e80629D572b1f200e6DF3586B3946A8A"
USDC_DECIMALS = 6

# ---------------------------------------------------------------------------
# Scoring Weights
# ---------------------------------------------------------------------------
CLAIMS_WINDOW_DAYS = 7
WEIGHT_CLAIMS = 0.6
WEIGHT_AVAILABILITY = 0.4

# ---------------------------------------------------------------------------
# Polygon RPC (ordered by priority)
# ---------------------------------------------------------------------------
POLYGON_RPC_ENDPOINTS = [
    os.getenv("POLYGON_RPC_URL"),           # Alchemy (recommended)
    "https://polygon-rpc.com",               # Fallback 1
    "https://rpc.ankr.com/polygon",          # Fallback 2
]

# Blocks per get_logs call (Alchemy ~2000, public ~1000)
LOG_QUERY_CHUNK_SIZE = int(os.getenv("LOG_CHUNK_SIZE", "2000"))

# Polygon: ~1 block per 2 seconds = ~43200 blocks/day
BLOCKS_PER_DAY = 43200

# ---------------------------------------------------------------------------
# Subnet Hyperparameters (set on-chain via btcli, documented here)
# ---------------------------------------------------------------------------
BURN_RATE = 0.9  # 90% of recycled TAO is burned

# ---------------------------------------------------------------------------
# Miner Config (from environment)
# ---------------------------------------------------------------------------
MINER_POLYGON_WALLET = os.getenv("POLYGON_WALLET")
MINER_POLYGON_KEY = os.getenv("POLYGON_PRIVATE_KEY")
MINER_API_URL = os.getenv("API_URL")
MARKETPLACE_URL = os.getenv("MARKETPLACE_URL", "https://www.handshake58.com")
