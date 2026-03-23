# Handshake58 Subnet 58 - Configuration
#
# Constants for Network Oracle, probe-based scoring.

import os

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
NETUID = 58

# ---------------------------------------------------------------------------
# Registry (Provider discovery for probing)
# ---------------------------------------------------------------------------
DEFAULT_REGISTRIES = [
    r.strip()
    for r in os.getenv(
        "REGISTRY_URLS",
        "https://handshake58.com/api/validator/registry"
    ).split(",")
    if r.strip()
]
REGISTRY_CACHE_FILE = os.getenv("REGISTRY_CACHE", "registry_cache.json")

# ---------------------------------------------------------------------------
# Probe Configuration
# ---------------------------------------------------------------------------
PROBE_TIMEOUT_MS = int(os.getenv("PROBE_TIMEOUT_MS", "5000"))
PROBE_CONCURRENCY = int(os.getenv("PROBE_CONCURRENCY", "10"))

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
ACCURACY_EMA_ALPHA = float(os.getenv("ACCURACY_EMA_ALPHA", "0.3"))

# ---------------------------------------------------------------------------
# Bittensor Tempo
# ---------------------------------------------------------------------------
TEMPO = 360
POLL_INTERVAL = 12

# ---------------------------------------------------------------------------
# Validator Weight Distribution
# ---------------------------------------------------------------------------
BURN_UID = 155
BURN_FRACTION = 0.9

# ---------------------------------------------------------------------------
# Auto-Update (self-hosted Docker)
# ---------------------------------------------------------------------------
AUTOUPDATE_ENABLED = os.getenv("AUTOUPDATE_ENABLED", "false").lower() == "true"
AUTOUPDATE_BRANCH = os.getenv("AUTOUPDATE_BRANCH", "main")
AUTOUPDATE_EXIT_CODE = 42

# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------
MARKETPLACE_URL = os.getenv("MARKETPLACE_URL", "https://www.handshake58.com")
