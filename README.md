# Handshake58 - Bittensor Subnet 58

[![CI](https://github.com/Handshake58/HS58-subnet/actions/workflows/ci.yml/badge.svg)](https://github.com/Handshake58/HS58-subnet/actions/workflows/ci.yml)

**Network Oracle: Decentralized provider monitoring for AI services.**

Miners probe provider endpoints worldwide. Validators score miners by consensus accuracy. Honest monitors earn TAO — no wallets, no staking, no provider setup needed.

---

## How It Works

```
Marketplace Registry ──► Validator ──► sends ProviderProbe to all Miners
                                        │
                         Miner A ◄──────┤──────► Miner B ◄──────┤──────► Miner C
                           │                        │                        │
                           ▼                        ▼                        ▼
                     HTTP GET probe           HTTP GET probe           HTTP GET probe
                     Provider URL             Provider URL             Provider URL
                           │                        │                        │
                           └────────────────────────┼────────────────────────┘
                                                    ▼
                                        Validator: Consensus
                                        (majority vote + median latency)
                                                    │
                                                    ▼
                                        Miner scores = accuracy vs consensus
                                        → EMA smoothed → Bittensor weights
```

### Roles

| Role | What it does | Requirements |
|------|-------------|--------------|
| **Miner** (Neutral Monitor) | Receives probe URLs from validators, performs HTTP GET, reports reachability + status + latency | VPS + internet |
| **Validator** (Miner Evaluator) | Sends probe tasks, computes consensus, scores miners by accuracy, sets weights | Staked TAO + VPERMIT |

### Scoring

Each epoch, the validator:

1. Fetches the provider list from the marketplace registry
2. **Deterministically** selects `PROBES_PER_ROUND` providers using the epoch's block hash as seed — all validators probe the same targets
3. Sends `ProviderProbe(target_url)` to all **active** miners (filters out validators and unreachable UIDs)
4. Computes **consensus**: majority vote on `reachable` + `status`
5. Scores each miner: `0.4 * reachable_match + 0.3 * status_match + 0.3 * latency_band`
6. Applies EMA smoothing (α=0.3) and sets weights on Bittensor with inclusion confirmation

The latency band is a binary check: `1.0` if response latency < `MAX_LATENCY_DEVIATION` (2000ms), `0.0` otherwise. This is deterministic across all validators regardless of geographic location.

### Anti-Gaming

| Attack | Why it fails |
|--------|-------------|
| Lie about reachability | Consensus detects disagreement — your score drops |
| Fake latency values | Binary band check; anything under threshold scores equally |
| Collude with other miners | Requires >50% of miners; validators can spot-check independently |
| Validator manipulates scores | Yuma consensus penalizes weight outliers |
| Validators set different weights | Deterministic sampling ensures all validators agree |

### Protocol Agnostic

The oracle monitors **all** provider types: DRAIN, MPP (x402), and any HTTP service. The miner just pings URLs — it doesn't know or care about the payment protocol. A `402 Payment Required` response is a valid "alive" signal for MPP providers.

---

## Prerequisites

- **Python** >= 3.9
- **btcli**: `pip install bittensor bittensor-cli`
- **TAO** in your coldkey wallet

No Polygon wallet, no RPC URL, no Alchemy subscription needed.

---

## Wallet Setup

```bash
pip install bittensor bittensor-cli

# Create coldkey (stores TAO)
btcli wallet new_coldkey --wallet.name hs58

# Create hotkey (used for subnet registration)
btcli wallet new_hotkey --wallet.name hs58 --wallet.hotkey default
```

Save your mnemonics securely. Check your address:

```bash
btcli wallet overview --wallet.name hs58
```

---

## Run a Miner

Miners are **Neutral Monitors**. No provider, no wallet, no registration — just probe URLs.

### Step 1: Register on Subnet 58

```bash
btcli subnet register --netuid 58 --wallet.name hs58 --wallet.hotkey default
```

### Step 2: Run

**Local:**
```bash
pip install -e .
python neurons/miner.py --netuid 58 --wallet.name hs58 --wallet.hotkey default
```

**Railway:**
1. Fork this repo → Railway → Deploy from GitHub → **Worker** service
2. Set environment variables:

```bash
BT_HOTKEY_B64=...
BT_COLDKEYPUB_B64=...
WALLET_NAME=hs58
HOTKEY_NAME=default
NEURON_TYPE=miner
AXON_PORT=8091
AXON_EXTERNAL_PORT=443
```

### Base64-Encode Wallet Files

**Linux / Mac:**
```bash
base64 -w 0 < ~/.bittensor/wallets/hs58/hotkeys/default
base64 -w 0 < ~/.bittensor/wallets/hs58/coldkeypub
```

**Windows PowerShell:**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\.bittensor\wallets\hs58\hotkeys\default"))
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\.bittensor\wallets\hs58\coldkeypub"))
```

---

## Run a Validator

### Step 1: Register + Stake

```bash
btcli subnet register --netuid 58 --wallet.name hs58 --wallet.hotkey default
btcli stake add --wallet.name hs58 --wallet.hotkey default --amount 100
```

### Step 2: Run

**Railway:**
```bash
BT_HOTKEY_B64=...
BT_COLDKEYPUB_B64=...
WALLET_NAME=hs58
HOTKEY_NAME=default
NEURON_TYPE=validator
```

**Docker (self-hosted, with auto-update):**
```bash
docker build -t hs58-validator .

docker run -d --restart unless-stopped \
  -e BT_HOTKEY_B64="$(base64 -w 0 < ~/.bittensor/wallets/hs58/hotkeys/default)" \
  -e BT_COLDKEYPUB_B64="$(base64 -w 0 < ~/.bittensor/wallets/hs58/coldkeypub)" \
  -e NEURON_TYPE=validator \
  -e WALLET_NAME=hs58 \
  -e HOTKEY_NAME=default \
  -e AUTOUPDATE_ENABLED=true \
  hs58-validator
```

---

## Configuration

| Variable | Default | Used by | Description |
|----------|---------|---------|-------------|
| `PROBE_TIMEOUT_MS` | `5000` | Miner | HTTP probe timeout in milliseconds |
| `REGISTRY_URLS` | `https://handshake58.com/api/validator/registry,https://mpp.dev/api/services` | Validator | Provider registry URLs (comma-separated, validators try them in order with cache fallback) |
| `REGISTRY_CACHE` | `registry_cache.json` | Validator | Local fallback cache file |
| `PROBES_PER_ROUND` | `5` | Validator | Random providers probed per epoch |
| `MAX_LATENCY_DEVIATION` | `2000` | Validator | Latency band threshold in ms (binary: below = pass) |
| `MARKETPLACE_URL` | `https://www.handshake58.com` | Validator | Marketplace for probe alerts |
| `AUTOUPDATE_ENABLED` | `false` | Both | Auto-update for Docker deployments |
| `AUTOUPDATE_BRANCH` | `main` | Both | Git branch to track |

---

## Architecture

```
HS58-subnet/
├── neurons/
│   ├── miner.py              # Neutral Monitor (HTTP probe)
│   └── validator.py           # Miner Evaluator (consensus scoring)
├── subnet58/
│   ├── __init__.py            # Version (2.1.1)
│   ├── protocol.py            # ProviderProbe Synapse (4 fields)
│   ├── config.py              # Oracle configuration constants
│   ├── registry_client.py     # Provider discovery + cache + alerts
│   ├── base/                  # Base classes (Bittensor template)
│   │   ├── neuron.py
│   │   ├── miner.py
│   │   └── validator.py
│   └── utils/
│       ├── config.py          # CLI args
│       └── misc.py
├── requirements.txt
├── setup.py
├── .env.example
├── Dockerfile
├── entrypoint.sh              # Wallet decode + neuron start
└── min_compute.yml
```

## Development

Run the unit tests locally:

```bash
pip install -e .[dev]
pytest tests/ -v
```

The CI suite covers the Yuma-proof v2.1.0 logic: deterministic provider sampling, the binary latency band, the registry failover chain, and the active-miner UID filter. Every push and pull request to `main` runs the suite on Python 3.9, 3.10, and 3.11.

## Related Projects

- [Handshake58 Marketplace](https://www.handshake58.com) — AI agent marketplace with provider directory
- [DRAIN Protocol](https://github.com/kimbo128/DRAIN) — Micropayment channels for AI services
- [drain-mcp](https://www.npmjs.com/package/drain-mcp) — Agent MCP server for DRAIN + MPP

## License

[PolyForm Shield 1.0](https://polyformproject.org/licenses/shield/1.0.0/) — Use, modify, and deploy for any purpose **except** building a competing product. See [LICENSE](LICENSE).
