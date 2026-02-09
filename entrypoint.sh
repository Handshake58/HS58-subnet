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

# Check if wallet keys are configured
if [ -z "$BT_HOTKEY_B64" ] || [ -z "$BT_COLDKEYPUB_B64" ]; then
    echo "[entrypoint] ================================================"
    echo "[entrypoint] Wallet keys not configured yet."
    echo "[entrypoint] Set these env vars and redeploy:"
    echo "[entrypoint]   BT_HOTKEY_B64"
    echo "[entrypoint]   BT_COLDKEYPUB_B64"
    echo "[entrypoint]   BT_COLDKEY_B64"
    echo "[entrypoint] ================================================"
    echo "[entrypoint] Waiting for configuration... (sleeping)"
    # Sleep forever so Railway doesn't restart-loop
    while true; do sleep 3600; done
fi

# Decode hotkey
echo "$BT_HOTKEY_B64" | base64 -d > "${WALLET_DIR}/hotkeys/${HOTKEY_NAME}"
echo "[entrypoint] Hotkey written to ${WALLET_DIR}/hotkeys/${HOTKEY_NAME}"

# Decode coldkey public
echo "$BT_COLDKEYPUB_B64" | base64 -d > "${WALLET_DIR}/coldkeypub"
echo "[entrypoint] Coldkeypub written"

# Decode coldkey encrypted (required for set_weights)
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
