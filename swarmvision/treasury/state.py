"""
SwarmVision Protocol — Treasury Epoch State

Accumulates operator metrics and revenue within an epoch.
Used by close_epoch() to build inputs for distribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict
import time

from swarmvision.treasury.distribution import OperatorStats, EpochLedger


@dataclass
class OperatorEpochAccum:
    uptime_seconds: int = 0
    ready_seconds: int = 0
    jobs_success: int = 0
    jobs_failure: int = 0
    poe_invalid: int = 0
    status: str = "active"


@dataclass
class TreasuryEpochState:
    epoch_id: str
    epoch_start_ts: int
    epoch_end_ts: int
    gross_revenue: Decimal = Decimal("0")
    refunds: Decimal = Decimal("0")
    operators: Dict[str, OperatorEpochAccum] = field(default_factory=dict)

    def ensure_operator(self, operator_ens: str) -> OperatorEpochAccum:
        if operator_ens not in self.operators:
            self.operators[operator_ens] = OperatorEpochAccum()
        return self.operators[operator_ens]

    def record_heartbeat(self, operator_ens: str, uptime_delta: int, ready_delta: int, status: str = "active") -> None:
        op = self.ensure_operator(operator_ens)
        op.uptime_seconds += max(0, int(uptime_delta))
        op.ready_seconds += max(0, int(ready_delta))
        op.status = status

    def record_job_charge(self, amount: Decimal) -> None:
        if amount < 0:
            return
        self.gross_revenue += amount

    def record_poe(self, operator_ens: str, success: bool, poe_valid: bool) -> None:
        op = self.ensure_operator(operator_ens)
        if not poe_valid:
            op.poe_invalid += 1
            return
        if success:
            op.jobs_success += 1
        else:
            op.jobs_failure += 1

    def to_ledger(self) -> EpochLedger:
        return EpochLedger(gross_revenue=self.gross_revenue, refunds=self.refunds)

    def to_operator_stats(self) -> list[OperatorStats]:
        out = []
        for ens, acc in self.operators.items():
            out.append(OperatorStats(
                operator_ens=ens,
                status=acc.status,
                uptime_seconds=acc.uptime_seconds,
                ready_seconds=acc.ready_seconds,
                jobs_success=acc.jobs_success,
                jobs_failure=acc.jobs_failure,
                poe_invalid=acc.poe_invalid,
            ))
        return out


def current_epoch_window(epoch_seconds: int) -> tuple[int, int]:
    now = int(time.time())
    start = now - (now % epoch_seconds)
    end = start + epoch_seconds
    return start, end
