# Contributing to Handshake58 Subnet 58

Thanks for considering a contribution. This document covers the basics
for getting a development environment running and the conventions we
follow when shipping changes to a subnet that handles real TAO.

## Development setup

```bash
git clone https://github.com/Handshake58/HS58-subnet.git
cd HS58-subnet
python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -e .[dev]
```

Run the test suite:

```bash
pytest tests/ -v
```

## Branching and pull requests

- Work on a feature branch off `main`.
- One logical change per pull request.
- Fill in the PR template, especially the **Yuma / consensus impact**
  section if you touch scoring, probe selection, or weight setting.
- All PRs must pass CI before review.

## Commit messages

We use a light Conventional Commits style:

```
<type>: <short summary>

<body explaining the why, not the what>
```

Common types: `feat`, `fix`, `test`, `docs`, `ci`, `refactor`,
`release`, `security`, `deps`.

## Code style

- Python 3.9+ compatible.
- Keep functions small and pure where possible. Validator scoring code
  must stay deterministic across validators (no wall-clock time, no
  unsourced randomness).
- Prefer explicit imports.
- Do not commit comments that just narrate what the code does.

## Tests

- New scoring or consensus logic must come with a unit test in `tests/`.
- Tests should not require network access. Mock `requests.get`,
  `subtensor`, and `dendrite` when needed.
- Avoid `time.sleep` in tests; use deterministic stubs instead.

## Yuma-relevant changes

A change is Yuma-relevant if it can cause two honest validators on the
same epoch to compute different scores or weights. Examples: probe
selection, latency scoring, EMA smoothing, miner UID filtering.

For Yuma-relevant changes:

1. Document the determinism argument in the PR description.
2. Add or extend a test in `tests/test_deterministic_sampling.py` or
   a sibling file demonstrating that two validators with identical
   inputs produce identical outputs.
3. Bump `spec_version` only if the change is truly incompatible with
   previously deployed validators.

## Releases

- Patch releases (`2.1.x`): bug fixes and resilience improvements that
  do not change protocol behaviour. No `spec_version` bump beyond what
  the version-string formula in `subnet58/__init__.py` produces.
- Minor releases (`2.x.0`): new features, scoring tweaks, optional
  config knobs.
- Major releases (`x.0.0`): breaking changes.

Always update `CHANGELOG.md` in the same commit as the version bump.

## Security

Please do not open public issues for security problems. See
[SECURITY.md](SECURITY.md) for the private reporting process.

## License

By contributing you agree that your contributions are licensed under
the [PolyForm Shield 1.0](https://polyformproject.org/licenses/shield/1.0.0/)
license used by the rest of the project.
