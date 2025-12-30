# Swarm Treasury Pool Distribution Spec

> **Protocol Version:** v0.2
> **Status:** FINAL

## 1. Goal

Distribute treasury revenue to `*.swarmcompute.eth` operators fairly, rewarding:

- **Executed work** (jobs)
- **Readiness** (always-on availability)
- **Reliability** (valid PoE, low failure)

And enforce:
- No PoE = no pay
- Suspended/inactive = excluded immediately

## 2. Terms

| Term | Definition |
|------|------------|
| **Epoch** | Fixed payout period (default: 24h UTC) |
| **Gross Revenue** | Total client charges captured during epoch |
| **Protocol Fees** | Optional fixed percentage for ops/dev (can be 0) |
| **Net Pool** | `gross - protocol_fees - refunds` |
| **Eligible Operator** | `role=operator`, `status=active` during epoch, meets minimum heartbeat |

## 3. Inputs (per epoch)

### 3.1 Revenue Ledger

For each job:
- `job_id`
- `client_ens`
- `unit_price` (decimal string)
- `operator_ens` (who executed)
- `poe_id` (must be valid)
- `timestamp`

### 3.2 Operator Telemetry

Per operator:
- `uptime_seconds` within epoch (from heartbeats)
- `ready_seconds` within epoch (declared "ready")
- `jobs_success` (valid PoE + success)
- `jobs_failure` (valid PoE + failure/partial)
- `poe_invalid_count` (should be 0)

## 4. Eligibility Rules

An operator is eligible if:
- ENS resolves and `status=active` at payout time
- `uptime_seconds >= MIN_UPTIME_SECONDS` (default: 6 hours)
- Has no severe violations

Jobs count only if:
- PoE validates
- Operator matches PoE identity
- Job was billed

## 5. Pool Split

Net Pool is split into:

| Pool | Default |
|------|---------|
| Work Pool | 70% |
| Readiness Pool | 30% |

## 6. Scoring

### 6.1 Work Score

```
work_units_i = jobs_success_i
work_score_i = work_units_i
```

### 6.2 Readiness Score

```
readiness_ratio_i = clamp(ready_seconds_i / epoch_seconds, 0..1)
uptime_ratio_i = clamp(uptime_seconds_i / epoch_seconds, 0..1)
readiness_score_i = (0.7 * readiness_ratio_i + 0.3 * uptime_ratio_i)
```

### 6.3 Reliability Penalty

```
failure_rate_i = jobs_failure_i / max(1, jobs_success_i + jobs_failure_i)
penalty_i = clamp(1 - failure_rate_i, 0.0..1.0)
```

Final scores:
```
final_work_score_i = work_score_i * penalty_i
final_ready_score_i = readiness_score_i * penalty_i
```

## 7. Payout Calculation

Let:
```
W = sum(final_work_score)
R = sum(final_ready_score)
```

Then:
```
work_payout_i = work_pool * (final_work_score_i / W) if W>0 else 0
ready_payout_i = readiness_pool * (final_ready_score_i / R) if R>0 else 0
gross_payout_i = work_payout_i + ready_payout_i
```

## 8. Caps & Dust

- **Optional cap:** `MAX_SHARE_PER_OPERATOR` (default: no cap)
- **Dust:** Amounts below `DUST_THRESHOLD` roll into next epoch

## 9. Determinism Requirements

- All currency amounts are Decimal strings
- All calculations use fixed precision (18 decimals)
- Final payouts rounded down
- Same inputs must produce identical outputs across machines

## 10. Reference Implementation

See: `swarmvision/treasury/distribution.py`

---

*This spec is FINAL for SwarmVision Protocol v0.2.*
