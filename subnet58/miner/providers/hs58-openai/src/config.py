import os
import math
from typing import Optional

import httpx
from dotenv import load_dotenv

from .types import ModelPricing, ProviderConfig

load_dotenv()

# In-memory model pricing (keyed by model id)
_active_models: dict[str, ModelPricing] = {}


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing env: {name}")
    return value


def _optional_env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _fetch_api_models(api_key: str) -> list[str]:
    response = httpx.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"OpenAI API error: {response.status_code}")
    data = response.json()
    items = data.get("data") or []
    return [item["id"] for item in items]


def _fetch_marketplace_pricing(
    marketplace_url: str,
) -> dict[str, dict[str, float]]:
    url = f"{marketplace_url.rstrip('/')}/api/directory/pricing?provider=openai"
    response = httpx.get(url, timeout=30.0)
    if response.status_code != 200:
        raise RuntimeError(f"Marketplace error: {response.status_code}")
    return response.json()


def _get_default_price(model_id: str) -> dict[str, float]:
    if "gpt-4o-mini" in model_id:
        return {"inputPerM": 0.15, "outputPerM": 0.60}
    if "gpt-4o" in model_id:
        return {"inputPerM": 2.50, "outputPerM": 10.00}
    if "gpt-4-turbo" in model_id:
        return {"inputPerM": 10.00, "outputPerM": 30.00}
    if "gpt-4" in model_id:
        return {"inputPerM": 30.00, "outputPerM": 60.00}
    if "gpt-3.5" in model_id:
        return {"inputPerM": 0.50, "outputPerM": 1.50}
    if "o1-mini" in model_id:
        return {"inputPerM": 3.00, "outputPerM": 12.00}
    if "o1" in model_id:
        return {"inputPerM": 15.00, "outputPerM": 60.00}
    if "o3-mini" in model_id:
        return {"inputPerM": 1.10, "outputPerM": 4.40}
    return {"inputPerM": 2.50, "outputPerM": 10.00}


def _is_chat_model(model_id: str) -> bool:
    return (
        model_id.startswith("gpt-")
        or model_id.startswith("o1")
        or model_id.startswith("o3")
    )


async def load_models(
    api_key: str, markup: float, marketplace_url: str
) -> None:
    """Load model list from OpenAI and pricing from Marketplace."""
    global _active_models
    print("Loading models from OpenAI API...")
    all_models = _fetch_api_models(api_key)
    api_models = [m for m in all_models if _is_chat_model(m)]
    print(f"  API returned {len(all_models)} models, {len(api_models)} are chat models")

    print("Fetching pricing from Marketplace...")
    pricing = _fetch_marketplace_pricing(marketplace_url)
    print(f"  Marketplace has {len(pricing)} prices configured")

    _active_models = {}
    for model_id in api_models:
        prices = pricing.get(model_id) or _get_default_price(model_id)
        used_fallback = model_id not in pricing
        input_per_1k = int(
            math.ceil((prices["inputPerM"] / 1000) * 1_000_000 * markup)
        )
        output_per_1k = int(
            math.ceil((prices["outputPerM"] / 1000) * 1_000_000 * markup)
        )
        _active_models[model_id] = {
            "inputPer1k": input_per_1k,
            "outputPer1k": output_per_1k,
        }
        print(
            f"  {model_id}: ${prices['inputPerM']}/{prices['outputPerM']} per M "
            f"{'(fallback)' if used_fallback else '✓'}"
        )

    if not _active_models:
        raise RuntimeError("No models available from OpenAI API")
    print(
        f"Loaded {len(_active_models)} models with {(markup - 1) * 100}% markup"
    )


def get_model_pricing(model: str) -> Optional[ModelPricing]:
    return _active_models.get(model)


def is_model_supported(model: str) -> bool:
    return model in _active_models


def get_supported_models() -> list[str]:
    return list(_active_models.keys())


def load_config() -> ProviderConfig:
    """Load provider config from environment."""
    chain_id = int(_optional_env("CHAIN_ID", "137"))
    if chain_id not in (137, 80002):
        raise RuntimeError(f"Invalid CHAIN_ID: {chain_id}")

    markup_percent = int(_optional_env("MARKUP_PERCENT", "50"))
    markup = 1 + (markup_percent / 100)

    # Support both PROVIDER_PRIVATE_KEY and POLYGON_PRIVATE_KEY for repo compatibility
    provider_key = os.environ.get("PROVIDER_PRIVATE_KEY") or os.environ.get(
        "POLYGON_PRIVATE_KEY"
    )
    if not provider_key:
        raise RuntimeError("Missing env: PROVIDER_PRIVATE_KEY or POLYGON_PRIVATE_KEY")

    return {
        "openaiApiKey": _require_env("OPENAI_API_KEY"),
        "port": int(_optional_env("PORT", "3000")),
        "host": _optional_env("HOST", "0.0.0.0"),
        "chainId": chain_id,
        "providerPrivateKey": provider_key,
        "polygonRpcUrl": os.environ.get("POLYGON_RPC_URL"),
        "claimThreshold": int(_optional_env("CLAIM_THRESHOLD", "1000000")),
        "storagePath": _optional_env("STORAGE_PATH", "./data/vouchers.json"),
        "markup": markup,
        "marketplaceUrl": _optional_env(
            "MARKETPLACE_URL", "https://handshake58.com"
        ),
        "providerName": _optional_env("PROVIDER_NAME", "HS58-OpenAI"),
        "autoClaimIntervalMinutes": int(
            _optional_env("AUTO_CLAIM_INTERVAL_MINUTES", "10")
        ),
        "autoClaimBufferSeconds": int(
            _optional_env("AUTO_CLAIM_BUFFER_SECONDS", "3600")
        ),
    }


def calculate_cost(
    pricing: ModelPricing, input_tokens: int, output_tokens: int
) -> int:
    """Cost in USDC base units (6 decimals)."""
    return (
        input_tokens * pricing["inputPer1k"]
        + output_tokens * pricing["outputPer1k"]
    ) // 1000
