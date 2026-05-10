# Security Policy

The Handshake58 team takes the security of Subnet 58 seriously. Because
miners and validators handle Bittensor wallet keys and on-chain weight
setting, vulnerabilities in this codebase can have direct economic
consequences for operators and the wider network.

## Supported Versions

Security fixes are applied to the latest minor release line on `main`.
Older release lines are not actively patched.

| Version | Status |
|---------|--------|
| 2.1.x   | Supported (active development) |
| 2.0.x   | End-of-life (please upgrade) |
| < 2.0   | End-of-life |

## Reporting a Vulnerability

**Please do not report security issues via public GitHub issues.**

Instead, report them privately using one of these channels:

1. **GitHub Security Advisories** (preferred):
   <https://github.com/Handshake58/HS58-subnet/security/advisories/new>
2. **Email**: `security@handshake58.com`

When reporting, please include:

- A description of the vulnerability and its impact
- Steps to reproduce or a proof of concept
- The affected version and any relevant configuration
- Whether the issue affects miners, validators, or both
- Your name or handle for credit (optional)

## Response Process

- We aim to acknowledge new reports within **72 hours**.
- We will work with you to understand and reproduce the issue.
- Critical issues affecting on-chain weight setting, wallet handling, or
  validator consensus will be prioritised and patched as quickly as possible.
- Once a fix is released, we will publish an advisory crediting the reporter
  unless anonymity is requested.

## Scope

In scope:

- The miner and validator code in this repository (`neurons/`, `subnet58/`)
- The `entrypoint.sh` and `Dockerfile` deployment surface
- Anything that could let an attacker steal wallet keys, manipulate
  consensus weights, or deny service to honest miners or validators

Out of scope:

- Vulnerabilities in upstream dependencies (please report to the upstream
  project; we will track and update once an upstream fix is available)
- Issues in the Handshake58 marketplace or oracle web pages — these belong
  to the marketplace repository, not this subnet
- Social engineering or compromised operator infrastructure

Thank you for helping keep Subnet 58 safe.
