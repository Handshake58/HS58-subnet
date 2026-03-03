# Contract Addresses
DRAIN_ADDRESSES: dict[int, str] = {
    137: "0x0C2B3aA1e80629D572b1f200e6DF3586B3946A8A",
    80002: "0x61f1C1E04d6Da1C92D0aF1a3d7Dc0fEFc8794d7C",
}

# USDC has 6 decimals
USDC_DECIMALS = 6

# EIP-712 Domain (name and version; chainId and verifyingContract set at runtime)
EIP712_DOMAIN = {
    "name": "DrainChannel",
    "version": "1",
}

# DrainChannel ABI (functions + errors + events) - web3.py format
DRAIN_CHANNEL_ABI = [
    {
        "inputs": [{"name": "channelId", "type": "bytes32"}],
        "name": "getChannel",
        "outputs": [
            {
                "components": [
                    {"name": "consumer", "type": "address"},
                    {"name": "provider", "type": "address"},
                    {"name": "deposit", "type": "uint256"},
                    {"name": "claimed", "type": "uint256"},
                    {"name": "expiry", "type": "uint256"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "channelId", "type": "bytes32"}],
        "name": "getBalance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "channelId", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
            {"name": "signature", "type": "bytes"},
        ],
        "name": "claim",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {"inputs": [], "name": "NotOwner", "type": "error"},
    {"inputs": [], "name": "NoOwner", "type": "error"},
    {"inputs": [], "name": "ZeroAddress", "type": "error"},
    {"inputs": [], "name": "ChannelExists", "type": "error"},
    {"inputs": [], "name": "ChannelNotFound", "type": "error"},
    {"inputs": [], "name": "NotProvider", "type": "error"},
    {"inputs": [], "name": "NotConsumer", "type": "error"},
    {"inputs": [], "name": "NotExpired", "type": "error"},
    {"inputs": [], "name": "InvalidSignature", "type": "error"},
    {"inputs": [], "name": "InvalidAmount", "type": "error"},
    {"inputs": [], "name": "TransferFailed", "type": "error"},
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "channelId", "type": "bytes32"},
            {"indexed": True, "name": "provider", "type": "address"},
            {"indexed": False, "name": "amount", "type": "uint256"},
        ],
        "name": "ChannelClaimed",
        "type": "event",
    },
    {
        "inputs": [
            {"name": "channelId", "type": "bytes32"},
            {"name": "finalAmount", "type": "uint256"},
            {"name": "providerSignature", "type": "bytes"},
        ],
        "name": "cooperativeClose",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "channelId", "type": "bytes32"},
            {"indexed": True, "name": "consumer", "type": "address"},
            {"indexed": False, "name": "refund", "type": "uint256"},
        ],
        "name": "ChannelClosed",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "channelId", "type": "bytes32"},
            {"indexed": True, "name": "recipient", "type": "address"},
            {"indexed": False, "name": "amount", "type": "uint256"},
        ],
        "name": "FeePaid",
        "type": "event",
    },
]

# Permanent claim failure errors -- will never succeed on retry
PERMANENT_CLAIM_ERRORS = (
    "InvalidAmount",
    "ChannelNotFound",
    "InvalidSignature",
    "NotProvider",
    "NotExpired",
)


def get_payment_headers(provider_address: str, chain_id: int) -> dict[str, str]:
    """Return headers for 402 payment required (matches TS getPaymentHeaders)."""
    return {
        "X-DRAIN-Error": "voucher_required",
        "X-Payment-Protocol": "drain-v2",
        "X-Payment-Provider": provider_address,
        "X-Payment-Contract": DRAIN_ADDRESSES[chain_id],
        "X-Payment-Chain": str(chain_id),
        "X-Payment-Signing": "https://handshake58.com/api/drain/signing",
        "X-Payment-Docs": "/v1/docs",
    }
