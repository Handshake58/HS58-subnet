<!--
Thanks for contributing to Subnet 58. Please fill in the sections below
so reviewers can quickly understand and validate your change.
-->

## Summary

<!-- What does this PR do, in 1-3 sentences? -->

## Motivation

<!-- Why is this change needed? Link related issues if any. -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Refactor / cleanup
- [ ] Documentation only
- [ ] Tests / CI only
- [ ] Breaking change (requires `spec_version` bump)

## Yuma / consensus impact

<!--
If the change touches scoring, probe selection, weight setting, or any
field used in `_probe_accuracy` / `_compute_consensus`:
- Does the new behaviour stay deterministic across all validators?
- Does it require a `spec_version` bump?
- Have you verified existing validators remain compatible?
-->

## Test plan

- [ ] `pytest tests/ -v` passes locally
- [ ] CI is green
- [ ] Manual test on testnet (if applicable)

## Checklist

- [ ] Updated `CHANGELOG.md`
- [ ] Updated `README.md` if user-facing config changed
- [ ] No secrets, hotkeys, or `.env` files committed
- [ ] Followed existing code style
