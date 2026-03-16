#!/bin/bash

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
    echo "[entrypoint]   BT_HOTKEY_B64 (required)"
    echo "[entrypoint]   BT_COLDKEYPUB_B64 (required)"
    echo "[entrypoint]   BT_COLDKEY_B64 (optional - only for staking/transfer from this wallet)"
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

# Decode coldkey (optional: set_weights is signed by hotkey; coldkey only needed for staking/transfer from this wallet)
if [ -z "$BT_COLDKEY_B64" ]; then
    echo "[entrypoint] BT_COLDKEY_B64 not set (optional - validator only needs hotkey + coldkeypub for set_weights)"
else
    echo "$BT_COLDKEY_B64" | base64 -d > "${WALLET_DIR}/coldkey"
    echo "[entrypoint] Coldkey written"
fi

echo "[entrypoint] Wallet setup complete."

# Auto-restart loop: restarts the neuron on crash with backoff (max 120s)
MAX_RESTART_DELAY=120
restart_delay=5

run_neuron() {
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

        AXON_PORT="${AXON_PORT:-8091}"
        echo "[entrypoint] Starting MINER (wallet=${POLYGON_WALLET}, api=${API_URL}, port=${AXON_PORT})..."

        MINER_ARGS="--netuid 58 --wallet.name $WALLET_NAME --wallet.hotkey $HOTKEY_NAME --axon.port $AXON_PORT --logging.debug"

        # If external host is set, resolve domain to IP (Bittensor only accepts IP addresses)
        if [ -n "$AXON_EXTERNAL_IP" ]; then
            if echo "$AXON_EXTERNAL_IP" | grep -qP '^\d+\.\d+\.\d+\.\d+$'; then
                RESOLVED_IP="$AXON_EXTERNAL_IP"
            else
                echo "[entrypoint] Resolving ${AXON_EXTERNAL_IP} to IP..."
                RESOLVED_IP=$(python3 -c "import socket; print(socket.getaddrinfo('${AXON_EXTERNAL_IP}', None, socket.AF_INET)[0][4][0])")
                echo "[entrypoint] Resolved to ${RESOLVED_IP}"
            fi
            MINER_ARGS="$MINER_ARGS --axon.external_ip $RESOLVED_IP"
        fi
        if [ -n "$AXON_EXTERNAL_PORT" ]; then
            MINER_ARGS="$MINER_ARGS --axon.external_port $AXON_EXTERNAL_PORT"
        else
            MINER_ARGS="$MINER_ARGS --axon.external_port $AXON_PORT"
        fi

        python neurons/miner.py $MINER_ARGS "$@"
    else
        echo "[entrypoint] Starting VALIDATOR (axon disabled - validators don't need incoming connections)..."
        python neurons/validator.py \
            --netuid 58 \
            --wallet.name "$WALLET_NAME" \
            --wallet.hotkey "$HOTKEY_NAME" \
            --neuron.axon_off \
            --logging.debug \
            "$@"
    fi
}

# Restart loop with exponential backoff
while true; do
    run_neuron "$@"
    exit_code=$?

    if [ $exit_code -eq 42 ]; then
        echo "[entrypoint] Auto-update triggered (exit code 42)."
        echo "[entrypoint] Pulling latest code..."
        cd /app
        git pull origin "${AUTOUPDATE_BRANCH:-main}" --ff-only
        echo "[entrypoint] Reinstalling package..."
        pip install --no-cache-dir -e .
        echo "[entrypoint] Update complete. Restarting immediately."
        restart_delay=5
        continue
    fi

    echo "[entrypoint] Neuron exited with code ${exit_code}. Restarting in ${restart_delay}s..."
    sleep $restart_delay
    # Exponential backoff, capped at MAX_RESTART_DELAY
    restart_delay=$((restart_delay * 2))
    if [ $restart_delay -gt $MAX_RESTART_DELAY ]; then
        restart_delay=$MAX_RESTART_DELAY
    fi
done
