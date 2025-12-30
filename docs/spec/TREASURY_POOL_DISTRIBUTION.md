# Swarm Treasury Pool Distribution Specification
SwarmVision Protocol v0.2

## Purpose
Define a deterministic, auditable mechanism to distribute Swarm Treasury revenue
to Microscalers (`*.swarmcompute.eth`) based on execution, readiness, and reliability.

This specification is implementation-independent but includes a reference
implementation in `swarmvision/treasury/distribution.py`.

## Epoch
- Fixed accounting window (default: 24h UTC)
- All calculations are epoch-scoped
- Same inputs MUST produce identical outputs

## Revenue Definitions
- Gross Revenue: Sum of client job charges
- Refunds: Client refunds in epoch
- Protocol Fee: Optional percentage
- Net Pool = Gross − Refunds − Protocol Fee

## Pool Split
- Work Pool: 70%
- Readiness Pool: 30%

## Eligibility
An operator is eligible if:
- ENS role = operator
- ENS status = active
- Uptime ≥ minimum threshold
- No invalid Proofs of Execution

## Scoring
Work Score:
- jobs_success

Readiness Score:
- 70% readiness ratio
- 30% uptime ratio

Reliability Penalty:
- 1 − failure_rate

## Payout
Final payout is proportional to:
- work_score × penalty
- readiness_score × penalty

All payouts use fixed-precision decimals.
Rounding is deterministic and downward only.

## Dust
Amounts below threshold may roll into the next epoch.

## Reference Implementation
See:
`swarmvision/treasury/distribution.py`
