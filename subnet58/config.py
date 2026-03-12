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
# DRAIN Scanning
# ---------------------------------------------------------------------------
CLAIMS_WINDOW_DAYS = 3

# ---------------------------------------------------------------------------
# Polygon RPC (ordered by priority)
# ---------------------------------------------------------------------------
POLYGON_RPC_ENDPOINTS = [
    os.getenv("POLYGON_RPC_URL"),           # Alchemy (recommended)
    "https://rpc.ankr.com/polygon",          # Fallback
]

# Blocks per get_logs call (Alchemy ~2000, public ~1000)
LOG_QUERY_CHUNK_SIZE = int(os.getenv("LOG_CHUNK_SIZE", "2000"))

# Polygon: ~1 block per 2 seconds = ~43200 blocks/day
BLOCKS_PER_DAY = 43200

# ---------------------------------------------------------------------------
# Validator Weight Distribution
# ---------------------------------------------------------------------------
BURN_UID = 15           # UID that receives the burn fraction of validator weights
BURN_FRACTION = 0.9     # 90% of weight goes to burn UID; remaining 10% split equally across WTA winners

# ---------------------------------------------------------------------------
# Miner Config (from environment)
# ---------------------------------------------------------------------------
MINER_POLYGON_WALLET = os.getenv("POLYGON_WALLET")
MINER_POLYGON_KEY = os.getenv("POLYGON_PRIVATE_KEY")
MINER_API_URL = os.getenv("API_URL")
MARKETPLACE_URL = os.getenv("MARKETPLACE_URL", "https://www.handshake58.com")
