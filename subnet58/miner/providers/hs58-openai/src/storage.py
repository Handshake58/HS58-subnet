import json
import os
from pathlib import Path
from typing import Any

from .types import ChannelState, StoredVoucher


class VoucherStorage:
    """Simple file-based storage for vouchers."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not os.path.isfile(self.file_path):
            return {
                "vouchers": [],
                "channels": {},
                "totalEarned": "0",
                "totalClaimed": "0",
            }
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            # Convert string amounts back to int in vouchers
            parsed["vouchers"] = [
                {
                    **v,
                    "amount": int(v["amount"]),
                    "nonce": int(v["nonce"]),
                }
                for v in parsed["vouchers"]
            ]
            # Convert string amounts back to int in channels
            for cid, ch in list(parsed["channels"].items()):
                ch["deposit"] = int(ch["deposit"])
                ch["totalCharged"] = int(ch["totalCharged"])
                if ch.get("lastVoucher"):
                    lv = ch["lastVoucher"]
                    lv["amount"] = int(lv["amount"])
                    lv["nonce"] = int(lv["nonce"])
            return parsed
        except Exception as e:
            print(f"Error loading storage, starting fresh: {e}")
            return {
                "vouchers": [],
                "channels": {},
                "totalEarned": "0",
                "totalClaimed": "0",
            }

    def _save(self) -> None:
        dir_path = Path(self.file_path).parent
        dir_path.mkdir(parents=True, exist_ok=True)
        serializable = {
            "vouchers": [
                {
                    **v,
                    "amount": str(v["amount"]),
                    "nonce": str(v["nonce"]),
                }
                for v in self.data["vouchers"]
            ],
            "channels": {
                cid: {
                    **ch,
                    "deposit": str(ch["deposit"]),
                    "totalCharged": str(ch["totalCharged"]),
                    "lastVoucher": (
                        {
                            **ch["lastVoucher"],
                            "amount": str(ch["lastVoucher"]["amount"]),
                            "nonce": str(ch["lastVoucher"]["nonce"]),
                        }
                        if ch.get("lastVoucher")
                        else None
                    ),
                }
                for cid, ch in self.data["channels"].items()
            },
            "totalEarned": self.data["totalEarned"],
            "totalClaimed": self.data["totalClaimed"],
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)

    def store_voucher(self, voucher: StoredVoucher) -> None:
        self.data["vouchers"].append(voucher)
        self._save()

    def get_channel(self, channel_id: str) -> ChannelState | None:
        return self.data["channels"].get(channel_id)

    def update_channel(self, channel_id: str, state: ChannelState) -> None:
        self.data["channels"][channel_id] = state
        self._save()

    def get_unclaimed_vouchers(self) -> list[StoredVoucher]:
        return [v for v in self.data["vouchers"] if not v.get("claimed")]

    def get_highest_voucher_per_channel(
        self,
    ) -> dict[str, StoredVoucher]:
        highest: dict[str, StoredVoucher] = {}
        for v in self.data["vouchers"]:
            if v.get("claimed"):
                continue
            cid = v["channelId"]
            if cid not in highest or v["amount"] > highest[cid]["amount"]:
                highest[cid] = v
        return highest

    def mark_claimed(self, channel_id: str, tx_hash: str) -> None:
        import time
        now_ms = int(time.time() * 1000)
        for v in self.data["vouchers"]:
            if v["channelId"] == channel_id and not v.get("claimed"):
                v["claimed"] = True
                v["claimedAt"] = now_ms
                v["claimTxHash"] = tx_hash
        self._save()

    def get_total_unclaimed(self) -> int:
        total = 0
        for v in self.get_highest_voucher_per_channel().values():
            total += v["amount"]
        return total

    def get_stats(self) -> dict[str, Any]:
        return {
            "totalVouchers": len(self.data["vouchers"]),
            "unclaimedVouchers": len(self.get_unclaimed_vouchers()),
            "activeChannels": len(self.data["channels"]),
            "totalEarned": int(self.data["totalEarned"]),
        }
