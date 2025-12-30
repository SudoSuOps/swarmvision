"""
Tests for Treasury Pool Distribution.

Validates the distribution algorithm per Treasury.distribution.md spec.
"""

import pytest
from decimal import Decimal

from swarmvision.treasury.distribution import (
    OperatorTelemetry,
    EpochInput,
    calculate_distribution,
    check_eligibility,
    compute_work_score,
    compute_readiness_score,
    compute_reliability_penalty,
    MIN_UPTIME_SECONDS,
    EPOCH_SECONDS,
)


class TestEligibility:
    """Test operator eligibility rules."""

    def test_active_operator_eligible(self):
        """Active operator with sufficient uptime is eligible."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            uptime_seconds=MIN_UPTIME_SECONDS + 1,
            status="active",
        )
        eligible, reason = check_eligibility("rig42.swarmcompute.eth", telemetry)
        assert eligible is True
        assert reason == "eligible"

    def test_inactive_operator_not_eligible(self):
        """Inactive operator is not eligible."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            uptime_seconds=MIN_UPTIME_SECONDS + 1,
            status="inactive",
        )
        eligible, reason = check_eligibility("rig42.swarmcompute.eth", telemetry)
        assert eligible is False
        assert "status=inactive" in reason

    def test_low_uptime_not_eligible(self):
        """Operator with low uptime is not eligible."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            uptime_seconds=MIN_UPTIME_SECONDS - 1,
            status="active",
        )
        eligible, reason = check_eligibility("rig42.swarmcompute.eth", telemetry)
        assert eligible is False
        assert "uptime=" in reason

    def test_invalid_poe_not_eligible(self):
        """Operator with invalid PoEs is not eligible."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            uptime_seconds=MIN_UPTIME_SECONDS + 1,
            status="active",
            poe_invalid_count=1,
        )
        eligible, reason = check_eligibility("rig42.swarmcompute.eth", telemetry)
        assert eligible is False
        assert "poe_invalid_count" in reason


class TestScoring:
    """Test scoring algorithms."""

    def test_work_score_equals_jobs_success(self):
        """Work score equals number of successful jobs."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            jobs_success=10,
            jobs_failure=2,
        )
        score = compute_work_score(telemetry)
        assert score == Decimal("10")

    def test_readiness_score_full_uptime(self):
        """Full uptime/readiness gives score of 1.0."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            uptime_seconds=EPOCH_SECONDS,
            ready_seconds=EPOCH_SECONDS,
        )
        score = compute_readiness_score(telemetry)
        assert score == Decimal("1")

    def test_readiness_score_zero_uptime(self):
        """Zero uptime gives score of 0."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            uptime_seconds=0,
            ready_seconds=0,
        )
        score = compute_readiness_score(telemetry)
        assert score == Decimal("0")

    def test_reliability_penalty_no_failures(self):
        """No failures = no penalty (1.0)."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            jobs_success=10,
            jobs_failure=0,
        )
        penalty = compute_reliability_penalty(telemetry)
        assert penalty == Decimal("1")

    def test_reliability_penalty_all_failures(self):
        """All failures = max penalty (0.0)."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            jobs_success=0,
            jobs_failure=10,
        )
        penalty = compute_reliability_penalty(telemetry)
        assert penalty == Decimal("0")

    def test_reliability_penalty_half_failures(self):
        """50% failure rate = 0.5 penalty."""
        telemetry = OperatorTelemetry(
            operator_ens="rig42.swarmcompute.eth",
            jobs_success=5,
            jobs_failure=5,
        )
        penalty = compute_reliability_penalty(telemetry)
        assert penalty == Decimal("0.5")


class TestDistribution:
    """Test full distribution calculation."""

    def test_basic_distribution(self):
        """Basic distribution with two operators."""
        epoch_input = EpochInput(
            epoch_id="epoch_001",
            epoch_start="2025-01-01T00:00:00Z",
            epoch_end="2025-01-02T00:00:00Z",
            gross_revenue=Decimal("1000"),
            protocol_fees=Decimal("0"),
            refunds=Decimal("0"),
            telemetry={
                "op1.swarmcompute.eth": OperatorTelemetry(
                    operator_ens="op1.swarmcompute.eth",
                    uptime_seconds=EPOCH_SECONDS,
                    ready_seconds=EPOCH_SECONDS,
                    jobs_success=10,
                    jobs_failure=0,
                    status="active",
                ),
                "op2.swarmcompute.eth": OperatorTelemetry(
                    operator_ens="op2.swarmcompute.eth",
                    uptime_seconds=EPOCH_SECONDS,
                    ready_seconds=EPOCH_SECONDS,
                    jobs_success=10,
                    jobs_failure=0,
                    status="active",
                ),
            },
        )

        result = calculate_distribution(epoch_input)

        assert result.net_pool == Decimal("1000")
        assert result.work_pool == Decimal("700")
        assert result.readiness_pool == Decimal("300")

        # Both operators should get equal payouts
        op1 = next(p for p in result.payouts if p.operator_ens == "op1.swarmcompute.eth")
        op2 = next(p for p in result.payouts if p.operator_ens == "op2.swarmcompute.eth")

        assert op1.eligible is True
        assert op2.eligible is True
        assert op1.gross_payout == op2.gross_payout
        assert op1.gross_payout > Decimal("0")

    def test_ineligible_operator_excluded(self):
        """Ineligible operator gets zero payout."""
        epoch_input = EpochInput(
            epoch_id="epoch_001",
            epoch_start="2025-01-01T00:00:00Z",
            epoch_end="2025-01-02T00:00:00Z",
            gross_revenue=Decimal("1000"),
            protocol_fees=Decimal("0"),
            refunds=Decimal("0"),
            telemetry={
                "active.swarmcompute.eth": OperatorTelemetry(
                    operator_ens="active.swarmcompute.eth",
                    uptime_seconds=EPOCH_SECONDS,
                    ready_seconds=EPOCH_SECONDS,
                    jobs_success=10,
                    status="active",
                ),
                "inactive.swarmcompute.eth": OperatorTelemetry(
                    operator_ens="inactive.swarmcompute.eth",
                    uptime_seconds=EPOCH_SECONDS,
                    ready_seconds=EPOCH_SECONDS,
                    jobs_success=10,
                    status="inactive",
                ),
            },
        )

        result = calculate_distribution(epoch_input)

        active = next(p for p in result.payouts if p.operator_ens == "active.swarmcompute.eth")
        inactive = next(p for p in result.payouts if p.operator_ens == "inactive.swarmcompute.eth")

        assert active.eligible is True
        assert active.gross_payout > Decimal("0")
        assert inactive.eligible is False
        assert inactive.gross_payout == Decimal("0")

    def test_protocol_fees_deducted(self):
        """Protocol fees reduce net pool."""
        epoch_input = EpochInput(
            epoch_id="epoch_001",
            epoch_start="2025-01-01T00:00:00Z",
            epoch_end="2025-01-02T00:00:00Z",
            gross_revenue=Decimal("1000"),
            protocol_fees=Decimal("100"),
            refunds=Decimal("0"),
            telemetry={
                "op1.swarmcompute.eth": OperatorTelemetry(
                    operator_ens="op1.swarmcompute.eth",
                    uptime_seconds=EPOCH_SECONDS,
                    ready_seconds=EPOCH_SECONDS,
                    jobs_success=10,
                    status="active",
                ),
            },
        )

        result = calculate_distribution(epoch_input)

        assert result.net_pool == Decimal("900")
        assert result.work_pool == Decimal("630")  # 900 * 0.7
        assert result.readiness_pool == Decimal("270")  # 900 * 0.3

    def test_empty_pool(self):
        """Zero net pool results in zero payouts."""
        epoch_input = EpochInput(
            epoch_id="epoch_001",
            epoch_start="2025-01-01T00:00:00Z",
            epoch_end="2025-01-02T00:00:00Z",
            gross_revenue=Decimal("100"),
            protocol_fees=Decimal("100"),
            refunds=Decimal("0"),
            telemetry={},
        )

        result = calculate_distribution(epoch_input)

        assert result.net_pool == Decimal("0")
        assert result.payouts == []
        assert result.total_distributed == Decimal("0")

    def test_dust_carryover(self):
        """Verify dust is calculated for carryover."""
        epoch_input = EpochInput(
            epoch_id="epoch_001",
            epoch_start="2025-01-01T00:00:00Z",
            epoch_end="2025-01-02T00:00:00Z",
            gross_revenue=Decimal("1000"),
            protocol_fees=Decimal("0"),
            refunds=Decimal("0"),
            telemetry={
                "op1.swarmcompute.eth": OperatorTelemetry(
                    operator_ens="op1.swarmcompute.eth",
                    uptime_seconds=EPOCH_SECONDS,
                    ready_seconds=EPOCH_SECONDS,
                    jobs_success=10,
                    status="active",
                ),
            },
        )

        result = calculate_distribution(epoch_input)

        # Total distributed + dust should equal net pool
        assert result.total_distributed + result.dust_carryover == result.net_pool


class TestDeterminism:
    """Test determinism requirements."""

    def test_same_inputs_same_outputs(self):
        """Same inputs must produce identical outputs."""
        epoch_input = EpochInput(
            epoch_id="epoch_001",
            epoch_start="2025-01-01T00:00:00Z",
            epoch_end="2025-01-02T00:00:00Z",
            gross_revenue=Decimal("1000.123456789012345678"),
            protocol_fees=Decimal("0"),
            refunds=Decimal("0"),
            telemetry={
                "op1.swarmcompute.eth": OperatorTelemetry(
                    operator_ens="op1.swarmcompute.eth",
                    uptime_seconds=EPOCH_SECONDS,
                    ready_seconds=EPOCH_SECONDS // 2,
                    jobs_success=7,
                    jobs_failure=3,
                    status="active",
                ),
            },
        )

        result1 = calculate_distribution(epoch_input)
        result2 = calculate_distribution(epoch_input)

        assert result1.net_pool == result2.net_pool
        assert result1.payouts[0].gross_payout == result2.payouts[0].gross_payout
        assert result1.dust_carryover == result2.dust_carryover
