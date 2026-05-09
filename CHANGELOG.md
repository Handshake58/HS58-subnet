# Changelog

All notable changes to Handshake58 Subnet 58 are documented here.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [SemVer](https://semver.org/spec/v2.0.0.html).

## [2.1.1] - 2026-05-09

### Added

- MPP.dev added as second default registry (`https://mpp.dev/api/services`).
  Validators now fail over `handshake58.com` -> `mpp.dev` -> local cache,
  hardening provider discovery against single-registry outages.
- Unit test suite covering Yuma-proof v2.1.0 invariants:
  deterministic provider sampling, binary latency band, registry failover,
  and the active-miner UID filter.
- GitHub Actions CI running pytest on Python 3.9, 3.10, and 3.11 for every
  push and pull request to `main`.
- `pip install -e .[dev]` extra for contributors, pulling pytest only.

### Changed

- `REGISTRY_URLS` default now lists both `handshake58.com` and `mpp.dev`,
  matching the dual-source model documented on the public oracle page.
  Operators that pin a single registry via the env var are unaffected.

### Notes

- Patch release. No protocol or scoring change.
- Existing validators and miners remain fully compatible without restart.

## [2.1.0] - Yuma-Proof

### Added

- Deterministic provider sampling using the epoch's block hash as RNG seed.
  All validators on the same epoch now select identical probe targets,
  which is required for Yuma weight agreement.
- Binary latency band (`< MAX_LATENCY_DEVIATION` -> 1.0, else 0.0) replaces
  the median-deviation latency score, removing geographic bias.
- Active miner UID filter: validators only probe UIDs with a reachable axon
  and never probe themselves.
- Weight inclusion confirmation (`wait_for_inclusion=True`) with retry on
  failure, ensuring weights actually land on chain.
- Auto-update via exit code 42 handled by `entrypoint.sh`.

### Changed

- EMA alpha default raised to 0.3 to match the documented behaviour.
- `min_compute.yml` and README updated to reflect Network Oracle scoring.

## [2.0.0] - Network Oracle

### Changed

- Replaced DRAIN-on-chain scoring with probe-based consensus scoring.
- Removed Polygon/RPC dependency from validators and miners.
- Marketplace-driven provider registry replaces local provider config.
