from typing import TypedDict, Optional


class ModelPricing(TypedDict):
    """Price per 1k tokens (USDC base units, 6 decimals)."""
    inputPer1k: int
    outputPer1k: int


class VoucherHeader(TypedDict):
    """Voucher from X-DRAIN-Voucher header."""
    channelId: str
    amount: str
    nonce: str
    signature: str


class StoredVoucher(TypedDict, total=False):
    """Stored voucher with metadata."""
    channelId: str
    amount: int
    nonce: int
    signature: str
    consumer: str
    receivedAt: int
    claimed: bool
    claimedAt: Optional[int]
    claimTxHash: Optional[str]


class ChannelState(TypedDict, total=False):
    """Channel state tracked by provider."""
    channelId: str
    consumer: str
    deposit: int
    totalCharged: int
    expiry: int
    lastVoucher: Optional[StoredVoucher]
    createdAt: int
    lastActivityAt: int


class ProviderConfig(TypedDict, total=False):
    """Provider configuration from env."""
    openaiApiKey: str
    port: int
    host: str
    chainId: int
    providerPrivateKey: str
    polygonRpcUrl: Optional[str]
    claimThreshold: int
    storagePath: str
    markup: float
    marketplaceUrl: str
    providerName: str
    autoClaimIntervalMinutes: int
    autoClaimBufferSeconds: int
