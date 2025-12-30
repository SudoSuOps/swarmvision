# SwarmVision Protocol v0.2 — Release Notes

## Highlights
- Established sovereign identity separation:
  - Clients: `*.swarmvision.eth`
  - Operators: `*.swarmcompute.eth`
- Added deterministic treasury pool distribution engine.
- Added Proof-of-Execution ingestion and verification hooks.
- Added signed payout reports for auditable accounting.

## Identity
- ENS identity resolution is protocol-grade:
  - role + status enforcement
  - owner + controller authorization
  - reserved label protections
  - immediate revocation semantics

## Treasury
- Added deterministic epoch payout computation:
  - Work Pool (70%)
  - Readiness Pool (30%)
  - Reliability penalty
  - Downward-only rounding
- Added `/treasury/epoch/close` endpoint:
  - closes epoch
  - returns signed payout report
  - rotates to next epoch

## Proof of Execution (PoE)
- Added `/poe/submit` endpoint:
  - canonical JSON hashing
  - EIP-191 signature recovery
  - binding to operator identity
- PoE drives operator stats for treasury eligibility.

## Security
- No email/password accounts.
- Signed actions and auditable payout reports.
- Designed for mesh-first deployment (Tailscale/Headscale).

## Upgrade Notes
- Rename operator identities from `*.swarmagent.eth` → `*.swarmcompute.eth`
- Ensure SwarmVision OS has `SWARMVISION_SIGNING_KEY` set.
- Recommended: use an ENS controller key for signing, not cold storage.

## Next (v0.3 Targets)
- Full PoE schema validation against JSON Schema
- Real ENS resolver integration (on-chain or CCIP-read)
- Operator heartbeat-driven uptime accounting
- Optional on-chain anchoring of payout report hashes
