# Subnet 58 — Task Tracking

## V2.1 — Yuma-Proof Update (current)

See `tasks/subnet-update-plan.md` for full analysis.

### Done

- [x] Deterministic provider sampling (block-hash seed) — all validators probe same targets
- [x] Binary latency band — deterministic across geographic locations
- [x] EMA alpha fix — default 0.3, matching documentation
- [x] Active miner filtering — only probe UIDs with reachable axons
- [x] Weight confirmation — wait_for_inclusion + retry on failure
- [x] Auto-update fix — entrypoint.sh handles exit code 42 with git pull
- [x] Version bump → 2.1.0
- [x] README + min_compute.yml updated

### Backlog (V2 — Anomaly Detection)

- [ ] LLM-powered quality analysis (see oracle page V2 section)
- [ ] Diagnosis Game: validators compete to explain failures
- [ ] Oracle Score: public validator reputation
- [ ] Ground truth hidden from validators
