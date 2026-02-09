#!/bin/bash
set -e

# ============================================================================
# Handshake58 Subnet 58 - Validator Entrypoint
#
# Decodes Bittensor wallet files from base64 env vars and starts the validator.
# ============================================================================

WALLET_NAME="${WALLET_NAME:-hs58}"
HOTKEY_NAME="${HOTKEY_NAME:-validator}"
WALLET_DIR="$HOME/.bittensor/wallets/${WALLET_NAME}"

echo "[entrypoint] Setting up wallet: ${WALLET_NAME} / ${HOTKEY_NAME}"

# Create wallet directory structure
mkdir -p "${WALLET_DIR}/hotkeys"

# Decode hotkey (REQUIRED)
if [ -z "$BT_HOTKEY_B64" ]; then
    echo "[entrypoint] ERROR: BT_HOTKEY_B64 env var is required"
    exit 1
fi
echo "$BT_HOTKEY_B64" | base64 -d > "${WALLET_DIR}/hotkeys/${HOTKEY_NAME}"
echo "[entrypoint] Hotkey written to ${WALLET_DIR}/hotkeys/${HOTKEY_NAME}"

# Decode coldkey public (REQUIRED)
if [ -z "$BT_COLDKEYPUB_B64" ]; then
    echo "[entrypoint] ERROR: BT_COLDKEYPUB_B64 env var is required"
    exit 1
fi
echo "$BT_COLDKEYPUB_B64" | base64 -d > "${WALLET_DIR}/coldkeypub"
echo "[entrypoint] Coldkeypub written"

# Decode coldkey encrypted (REQUIRED for set_weights)
if [ -z "$BT_COLDKEY_B64" ]; then
    echo "[entrypoint] WARNING: BT_COLDKEY_B64 not set - set_weights may fail"
else
    echo "$BT_COLDKEY_B64" | base64 -d > "${WALLET_DIR}/coldkey"
    echo "[entrypoint] Coldkey written"
fi

echo "[entrypoint] Wallet setup complete. Starting validator..."

# Start validator
exec python neurons/validator.py \
    --netuid 58 \
    --wallet.name "$WALLET_NAME" \
    --wallet.hotkey "$HOTKEY_NAME" \
    "$@"
