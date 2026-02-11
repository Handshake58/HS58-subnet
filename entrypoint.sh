#!/bin/bash
set -e

# ============================================================================
# Handshake58 Subnet 58 - Neuron Entrypoint
#
# Decodes Bittensor wallet files from base64 env vars and starts the neuron.
# Supports both validator and miner modes via NEURON_TYPE env var.
#
# NEURON_TYPE=validator (default) → neurons/validator.py
# NEURON_TYPE=miner               → neurons/miner.py
#   Miner also requires: POLYGON_WALLET, POLYGON_PRIVATE_KEY, API_URL
# ============================================================================

NEURON_TYPE="${NEURON_TYPE:-validator}"
WALLET_NAME="${WALLET_NAME:-hs58}"
HOTKEY_NAME="${HOTKEY_NAME:-validator}"
WALLET_DIR="$HOME/.bittensor/wallets/${WALLET_NAME}"

echo "[entrypoint] Neuron type: ${NEURON_TYPE}"
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

# Decode coldkey public (write both formats for bittensor compatibility)
echo "$BT_COLDKEYPUB_B64" | base64 -d > "${WALLET_DIR}/coldkeypub"
cp "${WALLET_DIR}/coldkeypub" "${WALLET_DIR}/coldkeypub.txt"
echo "[entrypoint] Coldkeypub written (coldkeypub + coldkeypub.txt)"

# Decode coldkey encrypted (required for set_weights / registration)
if [ -z "$BT_COLDKEY_B64" ]; then
    echo "[entrypoint] WARNING: BT_COLDKEY_B64 not set - set_weights may fail"
else
    echo "$BT_COLDKEY_B64" | base64 -d > "${WALLET_DIR}/coldkey"
    echo "[entrypoint] Coldkey written"
fi

echo "[entrypoint] Wallet setup complete."

# Start the appropriate neuron
if [ "$NEURON_TYPE" = "miner" ]; then
    # Validate miner-specific env vars
    if [ -z "$POLYGON_WALLET" ] || [ -z "$POLYGON_PRIVATE_KEY" ] || [ -z "$API_URL" ]; then
        echo "[entrypoint] ================================================"
        echo "[entrypoint] Miner requires additional env vars:"
        echo "[entrypoint]   POLYGON_WALLET       - Polygon wallet address"
        echo "[entrypoint]   POLYGON_PRIVATE_KEY   - Polygon private key (for ownership proof)"
        echo "[entrypoint]   API_URL              - Provider API endpoint URL"
        echo "[entrypoint] Optional:"
        echo "[entrypoint]   MARKETPLACE_URL      - Marketplace URL (default: https://www.handshake58.com)"
        echo "[entrypoint] ================================================"
        echo "[entrypoint] Waiting for configuration... (sleeping)"
        while true; do sleep 3600; done
    fi

    echo "[entrypoint] Starting MINER (wallet=${POLYGON_WALLET}, api=${API_URL})..."
    exec python neurons/miner.py \
        --netuid 58 \
        --wallet.name "$WALLET_NAME" \
        --wallet.hotkey "$HOTKEY_NAME" \
        "$@"
else
    echo "[entrypoint] Starting VALIDATOR..."
    exec python neurons/validator.py \
        --netuid 58 \
        --wallet.name "$WALLET_NAME" \
        --wallet.hotkey "$HOTKEY_NAME" \
        "$@"
fi
