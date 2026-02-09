# Handshake58 - Bittensor Subnet 58

**DRAIN Protocol scoring for AI providers on Bittensor.**

Providers who deliver real AI service (proven by DRAIN micropayments) earn TAO rewards. No fake-able metrics — if agents pay, the service works.

## How It Works

```
Agent → pays 1¢ session fee → Marketplace
Agent → opens DRAIN channel → Provider
Agent → uses AI, signs vouchers → Provider
Provider → claims vouchers on-chain → DrainChannel contract
Validator → scans ChannelClaimed events → scores Provider
Validator → sets weights → Bittensor
```

## Scoring (2 Metrics)

| Metric | Weight | Source | Window |
|---|---|---|---|
| **DRAIN Claims** | 60% | ChannelClaimed events on Polygon | 7 days rolling |
| **Availability** | 40% | Synapse response with wallet proof | Current |

Normalization: Relative to top provider (Bittensor standard).

## Anti-Gaming

| Attack | Why it fails |
|---|---|
| Fake ChannelClaimed | Provider can't sign as consumer |
| Self-booking | Must deposit real USDC + pay gas |
| Claim without service | Consumer won't sign vouchers |
| Steal other's claims | Claims tied to provider address |
| Fake wallet ownership | ECDSA signature verification |

## Quick Start

### Installation

```bash
git clone https://github.com/Handshake58/HS58-validator.git
cd HS58-validator
pip install -e .
```

### Run a Miner

1. Register on Bittensor Subnet 58:
```bash
btcli subnets register --netuid 58 --wallet.name YOUR_COLDKEY --wallet.hotkey YOUR_HOTKEY
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your Polygon wallet, private key, and API URL
```

3. Start the miner:
```bash
python neurons/miner.py --netuid 58 --wallet.name YOUR_COLDKEY --wallet.hotkey YOUR_HOTKEY
```

The miner will:
- Sign a wallet ownership proof (ECDSA)
- Auto-register on the Handshake58 marketplace
- Respond to validator checks

### Run a Validator

1. Register on Bittensor Subnet 58:
```bash
btcli subnets register --netuid 58 --wallet.name YOUR_COLDKEY --wallet.hotkey YOUR_HOTKEY
```

2. Configure environment:
```bash
cp .env.example .env
# Set POLYGON_RPC_URL (Alchemy recommended for reliable log queries)
```

3. Start the validator:
```bash
python neurons/validator.py --netuid 58 --wallet.name YOUR_COLDKEY --wallet.hotkey YOUR_HOTKEY
```

The validator will:
- Query all miners for wallet proofs
- Scan DRAIN ChannelClaimed events on Polygon (7-day window)
- Score miners: 60% claims + 40% availability
- Set weights on Bittensor

## Environment Variables

### Miner

| Variable | Required | Description |
|---|---|---|
| `POLYGON_WALLET` | Yes | Your Polygon wallet address (receives DRAIN payments) |
| `POLYGON_PRIVATE_KEY` | Yes | Private key for wallet ownership proof |
| `API_URL` | Yes | Your AI provider API endpoint |
| `MARKETPLACE_URL` | No | Marketplace URL (default: https://www.handshake58.com) |

### Validator

| Variable | Required | Description |
|---|---|---|
| `POLYGON_RPC_URL` | Recommended | Alchemy Polygon RPC for reliable event scanning |
| `LOG_CHUNK_SIZE` | No | Blocks per log query (default: 2000) |

## Architecture

```
HS58-validator/
├── neurons/
│   ├── miner.py              # Miner entry point
│   └── validator.py           # Validator entry point
├── subnet58/
│   ├── __init__.py            # Version
│   ├── protocol.py            # ProviderCheck Synapse (3 fields)
│   ├── config.py              # Constants (DRAIN address, scoring weights)
│   ├── base/                  # Base classes (from Bittensor template)
│   │   ├── neuron.py
│   │   ├── miner.py
│   │   └── validator.py
│   ├── utils/
│   │   ├── config.py          # CLI args and config
│   │   └── misc.py
│   └── validator/
│       └── drain_scanner.py   # DRAIN event scanner (chunked, multi-RPC)
├── requirements.txt
├── setup.py
├── .env.example
└── min_compute.yml
```

## DRAIN Protocol

**Contract:** `0x1C1918C99b6DcE977392E4131C91654d8aB71e64` (Polygon Mainnet)

The validator scans `ChannelClaimed(bytes32,address,uint256)` events to measure real provider usage.

## Related Projects

- [DRAIN Marketplace](https://github.com/Handshake58/DRAIN-marketplace) — Provider directory and agent discovery
- [Handshake58](https://www.handshake58.com) — Live marketplace

## TAO Rewards

| Recipient | Share |
|---|---|
| Miners | 41% |
| Validators | 41% |
| Subnet Owner | 18% |

Hardcoded in Yuma Consensus — not configurable.

## License

MIT License — see [LICENSE](LICENSE).
