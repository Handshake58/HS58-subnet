# Handshake58 Subnet 58 - Registry Client
#
# Validator-side provider discovery. Fetches provider list from marketplace
# registry, caches locally for resilience.

import json
import os
from typing import List, Dict, Optional

import requests
import bittensor as bt

from subnet58.config import (
    DEFAULT_REGISTRIES,
    REGISTRY_CACHE_FILE,
    MARKETPLACE_URL,
)


def fetch_providers(registries: Optional[List[str]] = None) -> List[Dict]:
    """
    Fetch provider list from registry APIs with local cache fallback.

    Tries each registry URL in order. On success, caches the result locally.
    If all registries fail, reads from the local cache file.

    Returns list of dicts with at least: id, probeUrl, name, protocol.
    """
    urls = registries or DEFAULT_REGISTRIES
    providers = None

    for url in urls:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            raw = data.get("providers", data.get("miners", []))
            providers = []
            for p in raw:
                probe_url = p.get("probeUrl") or p.get("apiUrl", "")
                if not probe_url:
                    continue
                providers.append({
                    "id": p.get("id", ""),
                    "probeUrl": probe_url,
                    "name": p.get("name", "unknown"),
                    "protocol": p.get("protocol", "drain"),
                })

            bt.logging.info(
                f"[Registry] {len(providers)} providers from {url}"
            )
            _save_cache(providers)
            return providers

        except Exception as e:
            bt.logging.warning(f"[Registry] {url} failed: {e}")
            continue

    cached = _load_cache()
    if cached is not None:
        bt.logging.info(
            f"[Registry] All registries down, using cache "
            f"({len(cached)} providers)"
        )
        return cached

    bt.logging.error("[Registry] No providers available (all registries down, no cache)")
    return []


def send_probe_alert(
    provider_id: str,
    probe_url: str,
    consensus_reachable: bool,
    marketplace_url: Optional[str] = None,
) -> None:
    """Report a probe failure to the marketplace (fire-and-forget)."""
    url = (marketplace_url or MARKETPLACE_URL) + "/api/validator/probe-alert"
    try:
        requests.post(
            url,
            json={
                "providerId": provider_id,
                "probeUrl": probe_url,
                "reachable": consensus_reachable,
            },
            timeout=5,
        )
    except Exception as e:
        bt.logging.trace(f"[Registry] probe-alert failed: {e}")


def _save_cache(providers: List[Dict]) -> None:
    try:
        with open(REGISTRY_CACHE_FILE, "w") as f:
            json.dump(providers, f)
    except Exception as e:
        bt.logging.trace(f"[Registry] Cache write failed: {e}")


def _load_cache() -> Optional[List[Dict]]:
    if not os.path.exists(REGISTRY_CACHE_FILE):
        return None
    try:
        with open(REGISTRY_CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None
