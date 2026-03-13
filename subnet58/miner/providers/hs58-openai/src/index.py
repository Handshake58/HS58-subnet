import json
import math
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

from .config import (
    load_config,
    load_models,
    calculate_cost,
    get_model_pricing,
    is_model_supported,
    get_supported_models,
)
from .constants import get_payment_headers
from .drain import DrainService
from .storage import VoucherStorage


def _format_units(value: int, decimals: int = 6) -> str:
    """Format USDC base units to human string (like viem formatUnits)."""
    if value == 0:
        return "0"
    divisor = 10**decimals
    whole = value // divisor
    frac = value % divisor
    if frac == 0:
        return str(whole)
    return f"{whole}.{str(frac).zfill(decimals).rstrip('0')}"


# Global state (set at startup)
config: Optional[dict] = None
storage: Optional[VoucherStorage] = None
drain_service: Optional[DrainService] = None
openai_client: Optional[AsyncOpenAI] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, storage, drain_service, openai_client
    config = load_config()
    storage = VoucherStorage(config["storagePath"])
    drain_service = DrainService(config, storage)
    openai_client = AsyncOpenAI(api_key=config["openaiApiKey"])
    await load_models(
        config["openaiApiKey"],
        config["markup"],
        config["marketplaceUrl"],
    )
    drain_service.start_auto_claim(
        config["autoClaimIntervalMinutes"],
        config["autoClaimBufferSeconds"],
    )
    print(
        f"{config['providerName']} | {len(get_supported_models())} models | "
        f"{(config['markup'] - 1) * 100}% markup | "
        f"http://{config['host']}:{config['port']}"
    )
    print(
        f"Auto-claim active: checking every {config['autoClaimIntervalMinutes']}min, "
        f"buffer {config['autoClaimBufferSeconds']}s"
    )
    yield
    # shutdown if needed


app = FastAPI(title="HS58-OpenAI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/v1/docs", response_class=PlainTextResponse)
def get_docs() -> str:
    models = get_supported_models()
    return (
        f"# {config['providerName']}\n\n"
        "Standard OpenAI-compatible chat completions API. Payment via DRAIN protocol.\n\n"
        "## Request Format\n\n"
        "POST /v1/chat/completions\n"
        "Header: X-DRAIN-Voucher (required)\n\n"
        '{"model": "<model-id>", "messages": [{"role": "user", "content": "Your message"}], "stream": false}\n\n'
        f"## Available Models ({len(models)})\n\n"
        "\n".join(models)
        + "\n\n## Pricing\n\nGET /v1/pricing for per-model token pricing.\n"
    )


@app.get("/v1/pricing")
def pricing() -> dict:
    pricing_map: dict[str, dict[str, str]] = {}
    for model in get_supported_models():
        p = get_model_pricing(model)
        if p:
            pricing_map[model] = {
                "inputPer1kTokens": _format_units(p["inputPer1k"], 6),
                "outputPer1kTokens": _format_units(p["outputPer1k"], 6),
            }
    return {
        "provider": drain_service.get_provider_address(),
        "providerName": config["providerName"],
        "chainId": config["chainId"],
        "currency": "USDC",
        "decimals": 6,
        "markup": f"{(config['markup'] - 1) * 100}%",
        "models": pricing_map,
    }


@app.get("/v1/models")
def models() -> dict:
    import time
    ts = int(time.time() * 1000)
    return {
        "object": "list",
        "data": [
            {
                "id": mid,
                "object": "model",
                "created": ts,
                "owned_by": config["providerName"].lower(),
            }
            for mid in get_supported_models()
        ],
    }


async def _stream_chat(
    model: str,
    messages: list,
    max_tokens: Optional[int],
    pricing: dict,
    voucher: dict,
    channel_state: dict,
) -> Any:
    """Generator for SSE stream."""
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if max_tokens is not None:
        create_kwargs["max_tokens"] = max_tokens
    stream = await openai_client.chat.completions.create(**create_kwargs)
    input_tokens = 0
    output_tokens = 0
    full_content = ""
    async for chunk in stream:
        content = (chunk.choices[0].delta.content or "") if chunk.choices else ""
        full_content += content
        if hasattr(chunk, "model_dump_json"):
            chunk_json = chunk.model_dump_json()
        elif hasattr(chunk, "model_dump"):
            chunk_json = json.dumps(chunk.model_dump())
        else:
            chunk_json = json.dumps(dict(chunk))
        yield f"data: {chunk_json}\n\n"
        if getattr(chunk, "usage", None):
            u = chunk.usage
            if u:
                input_tokens = getattr(u, "prompt_tokens", 0) or 0
                output_tokens = getattr(u, "completion_tokens", 0) or 0
    if input_tokens == 0:
        input_tokens = math.ceil(len(json.dumps(messages)) / 4)
    if output_tokens == 0:
        output_tokens = math.ceil(len(full_content) / 4)
    actual_cost = calculate_cost(pricing, input_tokens, output_tokens)
    drain_service.store_voucher(voucher, channel_state, actual_cost)
    remaining = (
        channel_state["deposit"]
        - channel_state["totalCharged"]
        - actual_cost
    )
    yield "data: [DONE]\n\n"
    yield f": X-DRAIN-Cost: {actual_cost}\n"
    yield f": X-DRAIN-Total: {channel_state['totalCharged'] + actual_cost}\n"
    yield f": X-DRAIN-Remaining: {remaining}\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    voucher_header = request.headers.get("x-drain-voucher")
    if not voucher_header:
        headers = get_payment_headers(
            drain_service.get_provider_address(), config["chainId"]
        )
        return JSONResponse(
            status_code=402,
            content={
                "error": {
                    "message": "X-DRAIN-Voucher header required",
                    "type": "payment_required",
                    "code": "voucher_required",
                }
            },
            headers=headers,
        )
    voucher = drain_service.parse_voucher_header(voucher_header)
    if not voucher:
        return JSONResponse(
            status_code=402,
            content={
                "error": {
                    "message": "Invalid X-DRAIN-Voucher format",
                    "type": "payment_required",
                    "code": "invalid_voucher_format",
                }
            },
            headers={"X-DRAIN-Error": "invalid_voucher_format"},
        )
    body = await request.json()
    model = body.get("model") or ""
    if not is_model_supported(model):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": f"Model '{model}' not supported. Available: {', '.join(get_supported_models())}",
                    "type": "invalid_request_error",
                    "code": "model_not_supported",
                }
            },
        )
    pricing = get_model_pricing(model)
    is_streaming = body.get("stream") is True
    max_output_cap: Optional[int] = config.get("maxOutputTokens")
    if max_output_cap is None:
        effective_max_tokens = body.get("max_tokens")
        estimate_output_tokens = 50
    else:
        effective_max_tokens = min(
            body.get("max_tokens") or max_output_cap,
            max_output_cap,
        )
        estimate_output_tokens = max_output_cap
    estimated_input_tokens = math.ceil(len(json.dumps(body.get("messages") or [])) / 4)
    estimated_min_cost = calculate_cost(
        pricing, estimated_input_tokens, estimate_output_tokens
    )
    validation = await drain_service.validate_voucher(voucher, estimated_min_cost)
    if not validation.get("valid"):
        err_headers = {"X-DRAIN-Error": validation.get("error", "validation_error")}
        if validation.get("error") == "insufficient_funds" and validation.get("channel"):
            err_headers["X-DRAIN-Required"] = str(estimated_min_cost)
            err_headers["X-DRAIN-Provided"] = str(
                int(voucher["amount"]) - validation["channel"]["totalCharged"]
            )
        return JSONResponse(
            status_code=402,
            content={
                "error": {
                    "message": f"Payment validation failed: {validation.get('error')}",
                    "type": "payment_required",
                    "code": validation.get("error", "validation_error"),
                }
            },
            headers=err_headers,
        )
    channel_state = validation["channel"]

    try:
        if is_streaming:
            return StreamingResponse(
                _stream_chat(
                    model,
                    body.get("messages") or [],
                    effective_max_tokens,
                    pricing,
                    voucher,
                    channel_state,
                ),
                media_type="text/event-stream",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-DRAIN-Channel": voucher["channelId"],
                },
            )
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": body.get("messages") or [],
        }
        if effective_max_tokens is not None:
            create_kwargs["max_tokens"] = effective_max_tokens
        completion = await openai_client.chat.completions.create(**create_kwargs)
        input_tokens = getattr(
            completion.usage, "prompt_tokens", None
        ) or 0
        output_tokens = getattr(
            completion.usage, "completion_tokens", None
        ) or 0
        actual_cost = calculate_cost(pricing, input_tokens, output_tokens)
        actual_validation = await drain_service.validate_voucher(
            voucher, actual_cost
        )
        if not actual_validation.get("valid"):
            return JSONResponse(
                status_code=402,
                content={
                    "error": {
                        "message": "Voucher insufficient for actual cost",
                        "type": "payment_required",
                        "code": "insufficient_funds_post",
                    }
                },
                headers={
                    "X-DRAIN-Error": "insufficient_funds_post",
                    "X-DRAIN-Required": str(actual_cost),
                },
            )
        drain_service.store_voucher(voucher, channel_state, actual_cost)
        remaining = (
            channel_state["deposit"]
            - channel_state["totalCharged"]
            - actual_cost
        )
        completion_dict = completion.model_dump() if hasattr(completion, "model_dump") else dict(completion)
        return JSONResponse(
            content=completion_dict,
            headers={
                "X-DRAIN-Cost": str(actual_cost),
                "X-DRAIN-Total": str(channel_state["totalCharged"] + actual_cost),
                "X-DRAIN-Remaining": str(remaining),
                "X-DRAIN-Channel": voucher["channelId"],
            },
        )
    except Exception as e:
        print("OpenAI API error:", e)
        msg = str(e) if isinstance(e, Exception) else "OpenAI API error"
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": msg,
                    "type": "api_error",
                    "code": "openai_error",
                }
            },
        )


@app.post("/v1/admin/claim")
async def admin_claim(force: str = "false"):
    try:
        force_all = force.lower() == "true"
        tx_hashes = await drain_service.claim_payments(force_all)
        return {
            "success": True,
            "claimed": len(tx_hashes),
            "transactions": tx_hashes,
            "forced": force_all,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e) if isinstance(e, Exception) else "Claim failed",
            },
        )


@app.get("/v1/admin/stats")
def admin_stats() -> dict:
    stats = storage.get_stats()
    return {
        "provider": drain_service.get_provider_address(),
        "providerName": config["providerName"],
        "chainId": config["chainId"],
        **stats,
        "totalEarned": _format_units(stats["totalEarned"], 6) + " USDC",
        "claimThreshold": _format_units(config["claimThreshold"], 6) + " USDC",
    }


@app.get("/v1/admin/vouchers")
def admin_vouchers() -> dict:
    unclaimed = storage.get_unclaimed_vouchers()
    highest = storage.get_highest_voucher_per_channel()
    from datetime import datetime
    channels = [
        {
            "channelId": cid,
            "amount": _format_units(v["amount"], 6) + " USDC",
            "amountRaw": str(v["amount"]),
            "nonce": str(v["nonce"]),
            "consumer": v["consumer"],
            "claimed": v.get("claimed", False),
            "receivedAt": datetime.utcfromtimestamp(v["receivedAt"] / 1000).isoformat() + "Z",
        }
        for cid, v in highest.items()
    ]
    return {
        "provider": drain_service.get_provider_address(),
        "providerName": config["providerName"],
        "unclaimedCount": len(unclaimed),
        "channels": channels,
    }


@app.post("/v1/close-channel")
async def close_channel(request: Request):
    try:
        body = await request.json()
        channel_id = body.get("channelId")
        if not channel_id:
            return JSONResponse(
                status_code=400,
                content={"error": "channelId required"},
            )
        result = await drain_service.sign_close_authorization(channel_id)
        return {
            "channelId": channel_id,
            "finalAmount": str(result["finalAmount"]),
            "signature": result["signature"],
        }
    except Exception as e:
        print("[close-channel] Error:", getattr(e, "message", e))
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error"},
        )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "provider": drain_service.get_provider_address(),
        "providerName": config["providerName"],
    }


@app.post("/v1/admin/refresh-models")
async def admin_refresh_models():
    try:
        await load_models(
            config["openaiApiKey"],
            config["markup"],
            config["marketplaceUrl"],
        )
        return {"success": True, "models": len(get_supported_models())}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e) if isinstance(e, Exception) else "unknown",
            },
        )


def run() -> None:
    import uvicorn
    cfg = load_config()
    uvicorn.run(
        "src.index:app",
        host=cfg["host"],
        port=cfg["port"],
        reload=False,
    )


if __name__ == "__main__":
    run()
