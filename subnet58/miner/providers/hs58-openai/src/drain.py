import time
from typing import Any, Optional

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import HexBytes

from .constants import (
    DRAIN_ADDRESSES,
    DRAIN_CHANNEL_ABI,
    EIP712_DOMAIN,
    PERMANENT_CLAIM_ERRORS,
)
from .storage import VoucherStorage
from .types import ChannelState, ProviderConfig, StoredVoucher, VoucherHeader


def _build_voucher_typed_data(
    chain_id: int,
    verifying_contract: str,
    channel_id: str,
    amount: int,
    nonce: int,
) -> dict[str, Any]:
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Voucher": [
                {"name": "channelId", "type": "bytes32"},
                {"name": "amount", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
            ],
        },
        "primaryType": "Voucher",
        "domain": {
            "name": EIP712_DOMAIN["name"],
            "version": EIP712_DOMAIN["version"],
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(verifying_contract),
        },
        "message": {
            "channelId": HexBytes(channel_id) if isinstance(channel_id, str) else channel_id,
            "amount": amount,
            "nonce": nonce,
        },
    }


def _build_close_typed_data(
    chain_id: int,
    verifying_contract: str,
    channel_id: str,
    final_amount: int,
) -> dict[str, Any]:
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "CloseAuthorization": [
                {"name": "channelId", "type": "bytes32"},
                {"name": "finalAmount", "type": "uint256"},
            ],
        },
        "primaryType": "CloseAuthorization",
        "domain": {
            "name": EIP712_DOMAIN["name"],
            "version": EIP712_DOMAIN["version"],
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(verifying_contract),
        },
        "message": {
            "channelId": HexBytes(channel_id) if isinstance(channel_id, str) else channel_id,
            "finalAmount": final_amount,
        },
    }


class DrainService:
    """DRAIN service for the provider."""

    def __init__(self, config: ProviderConfig, storage: VoucherStorage) -> None:
        self.config = config
        self.storage = storage
        rpc_url = config.get("polygonRpcUrl")
        if rpc_url:
            sanitized = rpc_url.rsplit("/", 1)[0] + "/***" if "/" in rpc_url else "***"
            print(f"[drain] Using custom RPC: {sanitized}")
        else:
            print(
                "[drain] WARNING: No POLYGON_RPC_URL set, using public RPC (rate-limited). "
                "Set POLYGON_RPC_URL for reliable claiming."
            )
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or "https://polygon-rpc.com"))
        self.account = Account.from_key(config["providerPrivateKey"])
        self.contract_address = Web3.to_checksum_address(
            DRAIN_ADDRESSES[config["chainId"]]
        )
        self.contract: Contract = self.w3.eth.contract(
            address=self.contract_address, abi=DRAIN_CHANNEL_ABI
        )
        self._auto_claim_thread: Optional[Any] = None

    def parse_voucher_header(self, header: str) -> Optional[VoucherHeader]:
        """Parse voucher from X-DRAIN-Voucher header."""
        try:
            import json
            parsed = json.loads(header)
            if not all(
                parsed.get(k)
                for k in ("channelId", "amount", "nonce", "signature")
            ):
                return None
            return {
                "channelId": parsed["channelId"],
                "amount": str(parsed["amount"]),
                "nonce": str(parsed["nonce"]),
                "signature": parsed["signature"],
            }
        except Exception:
            return None

    async def validate_voucher(
        self,
        voucher: VoucherHeader,
        required_amount: int,
    ) -> dict[str, Any]:
        """Validate voucher on-chain and EIP-712 signature."""
        try:
            amount = int(voucher["amount"])
            nonce = int(voucher["nonce"])

            # 1. Get channel from contract
            channel_data = self.contract.functions.getChannel(
                Web3.to_bytes(hexstr=voucher["channelId"])
            ).call()
            consumer, provider, deposit, claimed, expiry = channel_data

            # 2. Check channel exists
            if consumer == "0x0000000000000000000000000000000000000000":
                return {"valid": False, "error": "channel_not_found"}

            # 3. Check we are the provider
            if provider.lower() != self.account.address.lower():
                return {"valid": False, "error": "wrong_provider"}

            # 4. Get or create local channel state
            channel_state = self.storage.get_channel(voucher["channelId"])
            if channel_state is None:
                channel_state = {
                    "channelId": voucher["channelId"],
                    "consumer": consumer,
                    "deposit": deposit,
                    "totalCharged": 0,
                    "expiry": expiry,
                    "createdAt": int(time.time() * 1000),
                    "lastActivityAt": int(time.time() * 1000),
                }
            elif not channel_state.get("expiry"):
                channel_state["expiry"] = expiry

            # 5. Check voucher amount covers required
            previous_total = channel_state["totalCharged"]
            expected_total = previous_total + required_amount
            if amount < expected_total:
                return {
                    "valid": False,
                    "error": "insufficient_funds",
                    "channel": channel_state,
                }

            # 6. Check amount doesn't exceed deposit
            if amount > deposit:
                return {
                    "valid": False,
                    "error": "exceeds_deposit",
                    "channel": channel_state,
                }

            # 7. Check nonce
            last_v = channel_state.get("lastVoucher")
            if last_v and nonce <= last_v["nonce"]:
                return {
                    "valid": False,
                    "error": "invalid_nonce",
                    "channel": channel_state,
                }

            # 8. Verify EIP-712 signature
            typed_data = _build_voucher_typed_data(
                self.config["chainId"],
                self.contract_address,
                voucher["channelId"],
                amount,
                nonce,
            )
            signable = encode_typed_data(typed_data)
            sig = voucher["signature"]
            if isinstance(sig, str):
                sig = HexBytes(sig)
            recovered = Account.recover_message(signable, signature=sig)
            if recovered.lower() != consumer.lower():
                return {"valid": False, "error": "invalid_signature"}

            return {
                "valid": True,
                "channel": channel_state,
                "newTotal": amount,
            }
        except Exception as e:
            print(f"Voucher validation error: {e}")
            return {
                "valid": False,
                "error": str(e) if isinstance(e, Exception) else "validation_error",
            }

    def store_voucher(
        self,
        voucher: VoucherHeader,
        channel_state: ChannelState,
        cost: int,
    ) -> None:
        """Store a valid voucher and update channel state."""
        stored: StoredVoucher = {
            "channelId": voucher["channelId"],
            "amount": int(voucher["amount"]),
            "nonce": int(voucher["nonce"]),
            "signature": voucher["signature"],
            "consumer": channel_state["consumer"],
            "receivedAt": int(time.time() * 1000),
            "claimed": False,
        }
        channel_state["totalCharged"] = channel_state["totalCharged"] + cost
        channel_state["lastVoucher"] = stored
        channel_state["lastActivityAt"] = int(time.time() * 1000)
        self.storage.store_voucher(stored)
        self.storage.update_channel(voucher["channelId"], channel_state)

    def get_provider_address(self) -> str:
        return self.account.address

    def get_channel_balance(self, channel_id: str) -> int:
        return self.contract.functions.getBalance(
            Web3.to_bytes(hexstr=channel_id)
        ).call()

    def _handle_claim_error(
        self, context: str, channel_id: str, error: Exception
    ) -> None:
        error_name: Optional[str] = None
        if isinstance(error, ContractLogicError):
            error_name = getattr(error, "message", None) or str(error)
            for perm in PERMANENT_CLAIM_ERRORS:
                if perm in (error_name or ""):
                    error_name = perm
                    break
        if error_name and error_name in PERMANENT_CLAIM_ERRORS:
            print(
                f"[{context}] {channel_id}: {error_name} (permanent failure, marking as failed)"
            )
            self.storage.mark_claimed(channel_id, "0x0")
        else:
            short_msg = getattr(error, "message", str(error))
            print(f"[{context}] {channel_id}: {short_msg} (will retry)")

    async def claim_payments(self, force_all: bool = False) -> list[str]:
        """Claim payments for all channels above threshold."""
        tx_hashes: list[str] = []
        highest = self.storage.get_highest_voucher_per_channel()
        threshold = self.config["claimThreshold"]

        for channel_id, voucher in highest.items():
            if not force_all and voucher["amount"] < threshold:
                print(
                    f"Skipping channel {channel_id}: amount {voucher['amount']} "
                    f"below threshold {threshold}"
                )
                continue
            try:
                balance = self.get_channel_balance(voucher["channelId"])
                if balance == 0:
                    print(
                        f"Channel {channel_id}: on-chain balance is 0, marking as claimed"
                    )
                    self.storage.mark_claimed(channel_id, "0x0")
                    continue
            except Exception:
                pass
            try:
                tx = self.contract.functions.claim(
                    Web3.to_bytes(hexstr=voucher["channelId"]),
                    voucher["amount"],
                    voucher["nonce"],
                    HexBytes(voucher["signature"]),
                ).build_transaction(
                    {
                        "from": self.account.address,
                        "nonce": self.w3.eth.get_transaction_count(
                            self.account.address
                        ),
                    }
                )
                signed = self.account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hex = tx_hash.hex()
                self.storage.mark_claimed(channel_id, tx_hex)
                tx_hashes.append(tx_hex)
                print(f"Claimed {voucher['amount']} from channel {channel_id}: {tx_hex}")
            except Exception as e:
                self._handle_claim_error("claim", channel_id, e)
        return tx_hashes

    async def claim_expiring(
        self, buffer_seconds: int = 3600
    ) -> list[str]:
        """Claim channels expiring within buffer_seconds."""
        tx_hashes: list[str] = []
        highest = self.storage.get_highest_voucher_per_channel()
        now = int(time.time())

        for channel_id, voucher in highest.items():
            channel = self.storage.get_channel(channel_id)
            if not channel or not channel.get("expiry"):
                continue
            time_left = channel["expiry"] - now
            if time_left > buffer_seconds:
                continue
            if voucher["amount"] <= 0:
                continue
            try:
                balance = self.get_channel_balance(voucher["channelId"])
                if balance == 0:
                    print(
                        f"[auto-claim] Channel {channel_id}: on-chain balance is 0, already claimed"
                    )
                    self.storage.mark_claimed(channel_id, "0x0")
                    continue
            except Exception:
                pass
            status = (
                "EXPIRED"
                if time_left <= 0
                else f"expiring in {time_left // 60}min"
            )
            print(
                f"[auto-claim] Channel {channel_id} {status}, claiming {voucher['amount']}..."
            )
            try:
                tx = self.contract.functions.claim(
                    Web3.to_bytes(hexstr=voucher["channelId"]),
                    voucher["amount"],
                    voucher["nonce"],
                    HexBytes(voucher["signature"]),
                ).build_transaction(
                    {
                        "from": self.account.address,
                        "nonce": self.w3.eth.get_transaction_count(
                            self.account.address
                        ),
                    }
                )
                signed = self.account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hex = tx_hash.hex()
                self.storage.mark_claimed(channel_id, tx_hex)
                tx_hashes.append(tx_hex)
                print(
                    f"[auto-claim] Claimed {voucher['amount']} from {channel_id}: {tx_hex}"
                )
            except Exception as e:
                self._handle_claim_error("auto-claim", channel_id, e)
        return tx_hashes

    def start_auto_claim(
        self, interval_minutes: int = 10, buffer_seconds: int = 3600
    ) -> None:
        """Start background auto-claim loop (runs in a thread)."""
        import threading

        if self._auto_claim_thread is not None:
            return
        print(
            f"[auto-claim] Started: checking every {interval_minutes}min, "
            f"claiming channels expiring within {buffer_seconds / 60}min"
        )

        def _run() -> None:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.claim_expiring(buffer_seconds))
            except Exception as e:
                print(f"[auto-claim] Error on initial run: {e}")
            while True:
                time.sleep(interval_minutes * 60)
                try:
                    hashes = loop.run_until_complete(
                        self.claim_expiring(buffer_seconds)
                    )
                    if hashes:
                        print(
                            f"[auto-claim] Claimed {len(hashes)} expiring channel(s)"
                        )
                except Exception as e:
                    print(f"[auto-claim] Error during auto-claim check: {e}")

        self._auto_claim_thread = threading.Thread(target=_run, daemon=True)
        self._auto_claim_thread.start()

    async def sign_close_authorization(
        self, channel_id: str
    ) -> dict[str, Any]:
        """Sign close authorization for cooperative channel close."""
        highest = self.storage.get_highest_voucher_per_channel()
        voucher = highest.get(channel_id)
        final_amount = voucher["amount"] if voucher else 0
        typed_data = _build_close_typed_data(
            self.config["chainId"],
            self.contract_address,
            channel_id,
            final_amount,
        )
        signable = encode_typed_data(typed_data)
        signed = self.account.sign_message(signable)
        return {"finalAmount": final_amount, "signature": signed.signature.hex()}
