# Example OpenAI Provider Implementation

To run a Provider you can also use the [HS58 repo](https://github.com/Handshake58/HS58), which has template TypeScript implementations of many different Providers. 
The Python implementation here can serve as a foundation to write your own Provider in Python.

## Prerequisites
- Polygon wallet funded with POL for gas fees ([See Wallet Setup](https://github.com/Handshake58/HS58#wallet-setup))
- Dedicated RPC endpoint, recommended to reduce rate-limiting. See ([Polygon RPC Setup](https://github.com/Handshake58/HS58/blob/main/providers/README.md#polygon-rpc))
- OpenAI API key
- https compatible endpoint, required to get verified on the HS58 Marketplace

## Configure .env
Set the following in your `.env` in the repository root (copy from `.env.example`).
```bash
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
# --- Miner ---
# Your Polygon wallet address (receives DRAIN payments from agents)
POLYGON_WALLET=0x...
# Private key for the Polygon wallet (used to sign ownership proof)
POLYGON_PRIVATE_KEY=5...
# Your AI provider API URL (must serve /v1/pricing and /v1/chat/completions)
API_URL=https://your-provider.com
# Marketplace URL for auto-registration
MARKETPLACE_URL=https://www.handshake58.com

# --- Example OpenAI Provider ---
# OpenAI API key
OPENAI_API_KEY=sk-...
# Port to run the provider on
PORT=3000
HOST=0.0.0.0
CHAIN_ID=137
STORAGE_PATH=./data/vouchers.json
MARKUP_PERCENT=50
PROVIDER_NAME=HS58-OpenAI
CLAIM_THRESHOLD=1000000
AUTO_CLAIM_INTERVAL_MINUTES=10
AUTO_CLAIM_BUFFER_SECONDS=3600
# Cap on max_tokens per chat completion
MAX_OUTPUT_TOKENS=None
```
- **API_URL**: HTTPS URL where your provider is reachable (e.g. your deployed endpoint).
- **MAX_OUTPUT_TOKENS**: Cap on output tokens per completion; omit or set to `None` for no cap. 
- The POLYGON_RPC_URL, POLYGON_WALLET, and POLYGON_PRIVATE_KEY, can be obtained by following the READMEs linked in the Prerequisites.

## Install dependencies

Create a venv for the Provider and use the .toml file in this directory to install:

```bash
cd subnet58/miner/providers/hs58-openai
python -m venv .provider_venv
source .provider_venv/bin/activate
pip install -e .
```

## Run Provider

Change directory to the repository root so `.env` is picked up, then run the provider:

```bash
cd /path/to/HS58-subnet
hs58-openai
```

Once the provider is running, follow the [miner tutorial](../../../../README.md#step-2-register-on-subnet-58) in the main README. 
Note that if you are running the miner and Provider on the same machine, by default they use different venvs and different ports.
