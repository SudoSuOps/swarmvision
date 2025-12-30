"""
SwarmVision Protocol — Treasury Pool Distribution

Reference implementation for TREASURY_POOL_DISTRIBUTION.md spec.
Deterministic, auditable payout calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext, ROUND_DOWN
from typing import List, Optional

getcontext().prec = 50  # deterministic math


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def clamp(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class TreasuryConfig:
    epoch_seconds: int = 86400
    min_uptime_seconds: int = 21600
    work_pool_pct: Decimal = Decimal("0.70")
    readiness_pool_pct: Decimal = Decimal("0.30")
    protocol_fee_pct: Decimal = Decimal("0.00")
    payout_quant: Decimal = Decimal("0.00000001")
    dust_threshold: Decimal = Decimal("0.0001")
    max_share_per_operator: Optional[Decimal] = None


@dataclass(frozen=True)
class OperatorStats:
    operator_ens: str
    status: str
    uptime_seconds: int
    ready_seconds: int
    jobs_success: int
    jobs_failure: int
    poe_invalid: int = 0


@dataclass(frozen=True)
class EpochLedger:
    gross_revenue: Decimal
    refunds: Decimal = Decimal("0")


@dataclass(frozen=True)
class PayoutLine:
    operator_ens: str
    eligible: bool
    work_score: Decimal
    readiness_score: Decimal
    penalty: Decimal
    payout: Decimal


@dataclass(frozen=True)
class PayoutReport:
    epoch_seconds: int
    gross_revenue: Decimal
    protocol_fee: Decimal
    refunds: Decimal
    net_pool: Decimal
    work_pool: Decimal
    readiness_pool: Decimal
    payouts: List[PayoutLine]
    dust_rolled: Decimal


def _q(x: Decimal, q: Decimal) -> Decimal:
    return x.quantize(q, rounding=ROUND_DOWN)


def compute_epoch_payouts(
    ledger: EpochLedger,
    operators: List[OperatorStats],
    cfg: TreasuryConfig = TreasuryConfig(),
) -> PayoutReport:

    gross = ledger.gross_revenue
    refunds = ledger.refunds

    protocol_fee = _q(gross * cfg.protocol_fee_pct, cfg.payout_quant)
    net_pool = max(Decimal("0"), gross - refunds - protocol_fee)

    work_pool = _q(net_pool * cfg.work_pool_pct, cfg.payout_quant)
    readiness_pool = _q(net_pool * cfg.readiness_pool_pct, cfg.payout_quant)

    remainder = net_pool - (work_pool + readiness_pool)
    work_pool += remainder  # deterministic sink

    epoch = Decimal(cfg.epoch_seconds)

    scored = []

    for op in operators:
        eligible = (
            op.status == "active"
            and op.uptime_seconds >= cfg.min_uptime_seconds
            and op.poe_invalid == 0
        )

        work_score = Decimal(op.jobs_success) if eligible else Decimal("0")

        uptime_ratio = clamp(Decimal(op.uptime_seconds) / epoch, Decimal("0"), Decimal("1"))
        ready_ratio = clamp(Decimal(op.ready_seconds) / epoch, Decimal("0"), Decimal("1"))
        readiness_score = (
            Decimal("0.7") * ready_ratio + Decimal("0.3") * uptime_ratio
        ) if eligible else Decimal("0")

        denom = op.jobs_success + op.jobs_failure
        failure_rate = Decimal(op.jobs_failure) / Decimal(denom) if denom > 0 else Decimal("0")
        penalty = clamp(Decimal("1") - failure_rate, Decimal("0"), Decimal("1")) if eligible else Decimal("0")

        scored.append((op, eligible, work_score, readiness_score, penalty))

    total_work = sum(ws * p for _, _, ws, _, p in scored)
    total_ready = sum(rs * p for _, _, _, rs, p in scored)

    payouts: List[PayoutLine] = []
    allocated = Decimal("0")

    for op, eligible, ws, rs, p in scored:
        fw = ws * p
        fr = rs * p

        wp = work_pool * (fw / total_work) if eligible and total_work > 0 else Decimal("0")
        rp = readiness_pool * (fr / total_ready) if eligible and total_ready > 0 else Decimal("0")

        payout = _q(wp + rp, cfg.payout_quant)

        if cfg.max_share_per_operator and net_pool > 0:
            cap = _q(net_pool * cfg.max_share_per_operator, cfg.payout_quant)
            payout = min(payout, cap)

        payouts.append(PayoutLine(
            operator_ens=op.operator_ens,
            eligible=eligible,
            work_score=_q(fw, cfg.payout_quant),
            readiness_score=_q(fr, cfg.payout_quant),
            penalty=_q(p, cfg.payout_quant),
            payout=payout,
        ))

        allocated += payout

    dust = _q(net_pool - allocated, cfg.payout_quant)

    return PayoutReport(
        epoch_seconds=cfg.epoch_seconds,
        gross_revenue=_q(gross, cfg.payout_quant),
        protocol_fee=protocol_fee,
        refunds=_q(refunds, cfg.payout_quant),
        net_pool=_q(net_pool, cfg.payout_quant),
        work_pool=_q(work_pool, cfg.payout_quant),
        readiness_pool=_q(readiness_pool, cfg.payout_quant),
        payouts=sorted(payouts, key=lambda p: p.operator_ens),
        dust_rolled=max(dust, Decimal("0")),
    )
