"""
Tests for Treasury Pool Distribution.

Validates compute_epoch_payouts per TREASURY_POOL_DISTRIBUTION.md spec.
"""

import pytest
from decimal import Decimal

from swarmvision.treasury.distribution import (
    TreasuryConfig,
    OperatorStats,
    EpochLedger,
    compute_epoch_payouts,
    D,
)


EPOCH = 86400
MIN_UPTIME = 21600


def make_operator(
    ens: str,
    status: str = "active",
    uptime: int = EPOCH,
    ready: int = EPOCH,
    success: int = 10,
    failure: int = 0,
    poe_invalid: int = 0,
) -> OperatorStats:
    return OperatorStats(
        operator_ens=ens,
        status=status,
        uptime_seconds=uptime,
        ready_seconds=ready,
        jobs_success=success,
        jobs_failure=failure,
        poe_invalid=poe_invalid,
    )


class TestEligibility:
    """Test operator eligibility rules."""

    def test_active_operator_eligible(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth")]
        report = compute_epoch_payouts(ledger, ops)
        assert report.payouts[0].eligible is True

    def test_inactive_operator_not_eligible(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth", status="inactive")]
        report = compute_epoch_payouts(ledger, ops)
        assert report.payouts[0].eligible is False
        assert report.payouts[0].payout == Decimal("0")

    def test_low_uptime_not_eligible(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth", uptime=MIN_UPTIME - 1)]
        report = compute_epoch_payouts(ledger, ops)
        assert report.payouts[0].eligible is False

    def test_invalid_poe_not_eligible(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth", poe_invalid=1)]
        report = compute_epoch_payouts(ledger, ops)
        assert report.payouts[0].eligible is False


class TestPoolSplit:
    """Test pool splitting."""

    def test_default_split_70_30(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth")]
        report = compute_epoch_payouts(ledger, ops)
        # Work pool gets 70% + remainder
        assert report.work_pool + report.readiness_pool == report.net_pool

    def test_protocol_fee_deducted(self):
        cfg = TreasuryConfig(protocol_fee_pct=Decimal("0.10"))
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth")]
        report = compute_epoch_payouts(ledger, ops, cfg)
        assert report.protocol_fee == Decimal("100.00000000")
        assert report.net_pool == Decimal("900")

    def test_refunds_deducted(self):
        ledger = EpochLedger(gross_revenue=D(1000), refunds=D(100))
        ops = [make_operator("op1.swarmcompute.eth")]
        report = compute_epoch_payouts(ledger, ops)
        assert report.net_pool == Decimal("900")


class TestScoring:
    """Test scoring algorithms."""

    def test_work_score_equals_jobs_success(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth", success=10, failure=0)]
        report = compute_epoch_payouts(ledger, ops)
        # work_score = jobs_success * penalty (penalty=1 when no failures)
        assert report.payouts[0].work_score == Decimal("10.00000000")

    def test_penalty_reduces_score(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth", success=5, failure=5)]
        report = compute_epoch_payouts(ledger, ops)
        # 50% failure rate = 0.5 penalty
        assert report.payouts[0].penalty == Decimal("0.50000000")
        assert report.payouts[0].work_score == Decimal("2.50000000")  # 5 * 0.5


class TestDistribution:
    """Test payout distribution."""

    def test_equal_operators_equal_payout(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [
            make_operator("op1.swarmcompute.eth"),
            make_operator("op2.swarmcompute.eth"),
        ]
        report = compute_epoch_payouts(ledger, ops)
        assert report.payouts[0].payout == report.payouts[1].payout

    def test_ineligible_gets_zero(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [
            make_operator("active.swarmcompute.eth"),
            make_operator("inactive.swarmcompute.eth", status="inactive"),
        ]
        report = compute_epoch_payouts(ledger, ops)
        active = next(p for p in report.payouts if p.operator_ens == "active.swarmcompute.eth")
        inactive = next(p for p in report.payouts if p.operator_ens == "inactive.swarmcompute.eth")
        assert active.payout > Decimal("0")
        assert inactive.payout == Decimal("0")

    def test_max_share_cap(self):
        cfg = TreasuryConfig(max_share_per_operator=Decimal("0.50"))
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth")]
        report = compute_epoch_payouts(ledger, ops, cfg)
        # Single operator would get 100%, but capped at 50%
        assert report.payouts[0].payout <= Decimal("500")

    def test_dust_tracked(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [make_operator("op1.swarmcompute.eth")]
        report = compute_epoch_payouts(ledger, ops)
        # Total distributed + dust = net pool
        total_paid = sum(p.payout for p in report.payouts)
        assert total_paid + report.dust_rolled == report.net_pool

    def test_payouts_sorted_by_ens(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        ops = [
            make_operator("zzz.swarmcompute.eth"),
            make_operator("aaa.swarmcompute.eth"),
        ]
        report = compute_epoch_payouts(ledger, ops)
        assert report.payouts[0].operator_ens == "aaa.swarmcompute.eth"
        assert report.payouts[1].operator_ens == "zzz.swarmcompute.eth"


class TestDeterminism:
    """Test determinism requirements."""

    def test_same_inputs_same_outputs(self):
        ledger = EpochLedger(gross_revenue=D("1000.123456789"))
        ops = [
            make_operator("op1.swarmcompute.eth", success=7, failure=3),
            make_operator("op2.swarmcompute.eth", success=3, failure=1),
        ]
        r1 = compute_epoch_payouts(ledger, ops)
        r2 = compute_epoch_payouts(ledger, ops)
        assert r1.net_pool == r2.net_pool
        assert r1.payouts[0].payout == r2.payouts[0].payout
        assert r1.dust_rolled == r2.dust_rolled

    def test_empty_operators(self):
        ledger = EpochLedger(gross_revenue=D(1000))
        report = compute_epoch_payouts(ledger, [])
        assert report.payouts == []
        assert report.dust_rolled == report.net_pool

    def test_zero_revenue(self):
        ledger = EpochLedger(gross_revenue=D(0))
        ops = [make_operator("op1.swarmcompute.eth")]
        report = compute_epoch_payouts(ledger, ops)
        assert report.net_pool == Decimal("0")
        assert report.payouts[0].payout == Decimal("0")


def test_epoch_distribution_basic():
    """Integration test: more jobs = more payout."""
    cfg = TreasuryConfig(min_uptime_seconds=1)
    ledger = EpochLedger(gross_revenue=Decimal("100.00"))

    operators = [
        OperatorStats("rig1.swarmcompute.eth", "active", 86400, 86400, 70, 0),
        OperatorStats("rig2.swarmcompute.eth", "active", 86400, 86400, 30, 0),
    ]

    rpt = compute_epoch_payouts(ledger, operators, cfg)

    total = sum(p.payout for p in rpt.payouts) + rpt.dust_rolled
    assert total == rpt.net_pool

    rig1 = next(p for p in rpt.payouts if p.operator_ens.startswith("rig1"))
    rig2 = next(p for p in rpt.payouts if p.operator_ens.startswith("rig2"))

    assert rig1.payout > rig2.payout
