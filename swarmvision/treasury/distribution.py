"""
SwarmVision Protocol — Treasury Pool Distribution

Implements Treasury.distribution.md spec (v0.2 FINAL).

Distributes treasury revenue to *.swarmcompute.eth operators fairly:
- Executed work (jobs)
- Readiness (always-on availability)
- Reliability (valid PoE, low failure)

No PoE = no pay. Suspended/inactive = excluded.

All calculations use Decimal for determinism.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Optional
import json


# =============================================================================
# CONSTANTS
# =============================================================================

# Epoch duration in seconds (default: 24 hours)
EPOCH_SECONDS = 86400

# Minimum uptime to qualify (default: 6 hours)
MIN_UPTIME_SECONDS = 21600

# Pool split ratios
WORK_POOL_RATIO = Decimal("0.70")
READINESS_POOL_RATIO = Decimal("0.30")

# Readiness score weights
READY_WEIGHT = Decimal("0.7")
UPTIME_WEIGHT = Decimal("0.3")

# Dust threshold (amounts below this roll to next epoch)
DUST_THRESHOLD = Decimal("0.000001")

# Precision for all calculations
PRECISION = Decimal("0.000000000000000001")  # 18 decimals


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class JobRecord:
    """A single job from the revenue ledger."""
    job_id: str
    client_ens: str
    unit_price: Decimal
    operator_ens: str
    poe_id: str
    timestamp: str


@dataclass
class OperatorTelemetry:
    """Telemetry data for one operator during an epoch."""
    operator_ens: str
    uptime_seconds: int = 0
    ready_seconds: int = 0
    jobs_success: int = 0
    jobs_failure: int = 0
    poe_invalid_count: int = 0
    status: str = "active"  # From ENS text record


@dataclass
class EpochInput:
    """All inputs for one epoch's distribution."""
    epoch_id: str
    epoch_start: str
    epoch_end: str
    gross_revenue: Decimal
    protocol_fees: Decimal
    refunds: Decimal
    jobs: list[JobRecord] = field(default_factory=list)
    telemetry: dict[str, OperatorTelemetry] = field(default_factory=dict)


@dataclass
class OperatorPayout:
    """Computed payout for one operator."""
    operator_ens: str
    work_payout: Decimal
    readiness_payout: Decimal
    gross_payout: Decimal
    work_score: Decimal
    readiness_score: Decimal
    penalty: Decimal
    eligible: bool
    reason: str = ""


@dataclass
class EpochResult:
    """Result of distribution calculation."""
    epoch_id: str
    net_pool: Decimal
    work_pool: Decimal
    readiness_pool: Decimal
    payouts: list[OperatorPayout]
    dust_carryover: Decimal
    total_distributed: Decimal


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def clamp(value: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    """Clamp a value to a range."""
    return max(min_val, min(max_val, value))


def to_decimal(value) -> Decimal:
    """Convert any value to Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError(f"Cannot convert {type(value)} to Decimal")


# =============================================================================
# ELIGIBILITY
# =============================================================================

def check_eligibility(
    operator_ens: str,
    telemetry: OperatorTelemetry,
    min_uptime: int = MIN_UPTIME_SECONDS
) -> tuple[bool, str]:
    """
    Check if operator is eligible for distribution.

    From spec section 4:
    - ENS resolves and status=active at payout time
    - uptime_seconds >= MIN_UPTIME_SECONDS (default: 6 hours)
    - Has no severe violations

    Returns (eligible, reason).
    """
    # Check status
    if telemetry.status != "active":
        return False, f"status={telemetry.status}"

    # Check uptime
    if telemetry.uptime_seconds < min_uptime:
        return False, f"uptime={telemetry.uptime_seconds}s < {min_uptime}s"

    # Check for invalid PoEs (severe violation)
    if telemetry.poe_invalid_count > 0:
        return False, f"poe_invalid_count={telemetry.poe_invalid_count}"

    return True, "eligible"


# =============================================================================
# SCORING
# =============================================================================

def compute_work_score(telemetry: OperatorTelemetry) -> Decimal:
    """
    Compute work score.

    From spec section 6.1:
    work_score = jobs_success
    """
    return Decimal(telemetry.jobs_success)


def compute_readiness_score(
    telemetry: OperatorTelemetry,
    epoch_seconds: int = EPOCH_SECONDS
) -> Decimal:
    """
    Compute readiness score.

    From spec section 6.2:
    readiness_ratio = clamp(ready_seconds / epoch_seconds, 0..1)
    uptime_ratio = clamp(uptime_seconds / epoch_seconds, 0..1)
    readiness_score = 0.7 * readiness_ratio + 0.3 * uptime_ratio
    """
    epoch_dec = Decimal(epoch_seconds)

    readiness_ratio = clamp(
        Decimal(telemetry.ready_seconds) / epoch_dec,
        Decimal("0"),
        Decimal("1")
    )

    uptime_ratio = clamp(
        Decimal(telemetry.uptime_seconds) / epoch_dec,
        Decimal("0"),
        Decimal("1")
    )

    return READY_WEIGHT * readiness_ratio + UPTIME_WEIGHT * uptime_ratio


def compute_reliability_penalty(telemetry: OperatorTelemetry) -> Decimal:
    """
    Compute reliability penalty.

    From spec section 6.3:
    failure_rate = jobs_failure / max(1, jobs_success + jobs_failure)
    penalty = clamp(1 - failure_rate, 0..1)
    """
    total_jobs = telemetry.jobs_success + telemetry.jobs_failure
    if total_jobs == 0:
        return Decimal("1")  # No jobs = no penalty

    failure_rate = Decimal(telemetry.jobs_failure) / Decimal(max(1, total_jobs))

    return clamp(
        Decimal("1") - failure_rate,
        Decimal("0"),
        Decimal("1")
    )


# =============================================================================
# DISTRIBUTION ALGORITHM
# =============================================================================

def calculate_distribution(
    epoch_input: EpochInput,
    dust_from_previous: Decimal = Decimal("0")
) -> EpochResult:
    """
    Calculate distribution for one epoch.

    From spec section 7:
    1. Compute net_pool = gross - protocol_fees - refunds
    2. Split into work_pool (70%) and readiness_pool (30%)
    3. Score each eligible operator
    4. Distribute proportionally
    5. Handle dust carryover

    All calculations use Decimal for determinism.
    """
    # Step 1: Compute net pool
    net_pool = (
        epoch_input.gross_revenue
        - epoch_input.protocol_fees
        - epoch_input.refunds
        + dust_from_previous
    )

    if net_pool <= Decimal("0"):
        return EpochResult(
            epoch_id=epoch_input.epoch_id,
            net_pool=net_pool,
            work_pool=Decimal("0"),
            readiness_pool=Decimal("0"),
            payouts=[],
            dust_carryover=Decimal("0"),
            total_distributed=Decimal("0"),
        )

    # Step 2: Split pools
    work_pool = net_pool * WORK_POOL_RATIO
    readiness_pool = net_pool * READINESS_POOL_RATIO

    # Step 3: Score operators
    payouts: list[OperatorPayout] = []
    total_work_score = Decimal("0")
    total_ready_score = Decimal("0")

    for operator_ens, telemetry in epoch_input.telemetry.items():
        # Check eligibility
        eligible, reason = check_eligibility(operator_ens, telemetry)

        if not eligible:
            payouts.append(OperatorPayout(
                operator_ens=operator_ens,
                work_payout=Decimal("0"),
                readiness_payout=Decimal("0"),
                gross_payout=Decimal("0"),
                work_score=Decimal("0"),
                readiness_score=Decimal("0"),
                penalty=Decimal("0"),
                eligible=False,
                reason=reason,
            ))
            continue

        # Compute scores
        work_score = compute_work_score(telemetry)
        readiness_score = compute_readiness_score(telemetry)
        penalty = compute_reliability_penalty(telemetry)

        final_work_score = work_score * penalty
        final_ready_score = readiness_score * penalty

        total_work_score += final_work_score
        total_ready_score += final_ready_score

        payouts.append(OperatorPayout(
            operator_ens=operator_ens,
            work_payout=Decimal("0"),  # Filled in step 4
            readiness_payout=Decimal("0"),
            gross_payout=Decimal("0"),
            work_score=final_work_score,
            readiness_score=final_ready_score,
            penalty=penalty,
            eligible=True,
        ))

    # Step 4: Calculate payouts
    total_distributed = Decimal("0")

    for payout in payouts:
        if not payout.eligible:
            continue

        # Work payout
        if total_work_score > Decimal("0"):
            payout.work_payout = (
                work_pool * payout.work_score / total_work_score
            ).quantize(PRECISION, rounding=ROUND_DOWN)
        else:
            payout.work_payout = Decimal("0")

        # Readiness payout
        if total_ready_score > Decimal("0"):
            payout.readiness_payout = (
                readiness_pool * payout.readiness_score / total_ready_score
            ).quantize(PRECISION, rounding=ROUND_DOWN)
        else:
            payout.readiness_payout = Decimal("0")

        payout.gross_payout = payout.work_payout + payout.readiness_payout
        total_distributed += payout.gross_payout

    # Step 5: Calculate dust carryover
    dust_carryover = net_pool - total_distributed

    # Filter out dust payouts
    for payout in payouts:
        if payout.gross_payout < DUST_THRESHOLD:
            dust_carryover += payout.gross_payout
            payout.work_payout = Decimal("0")
            payout.readiness_payout = Decimal("0")
            payout.gross_payout = Decimal("0")

    return EpochResult(
        epoch_id=epoch_input.epoch_id,
        net_pool=net_pool,
        work_pool=work_pool,
        readiness_pool=readiness_pool,
        payouts=payouts,
        dust_carryover=dust_carryover,
        total_distributed=total_distributed,
    )


# =============================================================================
# SERIALIZATION (for determinism verification)
# =============================================================================

def result_to_dict(result: EpochResult) -> dict:
    """Convert result to JSON-serializable dict."""
    return {
        "epoch_id": result.epoch_id,
        "net_pool": str(result.net_pool),
        "work_pool": str(result.work_pool),
        "readiness_pool": str(result.readiness_pool),
        "dust_carryover": str(result.dust_carryover),
        "total_distributed": str(result.total_distributed),
        "payouts": [
            {
                "operator_ens": p.operator_ens,
                "work_payout": str(p.work_payout),
                "readiness_payout": str(p.readiness_payout),
                "gross_payout": str(p.gross_payout),
                "work_score": str(p.work_score),
                "readiness_score": str(p.readiness_score),
                "penalty": str(p.penalty),
                "eligible": p.eligible,
                "reason": p.reason,
            }
            for p in result.payouts
        ],
    }


def result_to_json(result: EpochResult) -> str:
    """Convert result to canonical JSON (for determinism checks)."""
    return json.dumps(
        result_to_dict(result),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
