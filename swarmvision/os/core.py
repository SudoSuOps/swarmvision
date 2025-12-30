#!/usr/bin/env python3
"""
SwarmVision Protocol — OS Core

The SwarmVision OS is the coordination layer:
- Job intake and routing
- Agent registration and heartbeats
- Proof verification
- Treasury accounting

This is a FastAPI application that serves as the central coordinator.
In production, this could be decentralized or replicated.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from swarmvision.identity.ens import (
    get_identity_service,
    resolve_identity,
    verify_operator,
    verify_client,
)
from swarmvision.identity.crypto import verify_proof_signature
from swarmvision.identity.poe import validate_poe, extract_poe_metrics
from swarmvision.treasury.pool import get_treasury, JOB_COST
from swarmvision.treasury.distribution import (
    compute_epoch_payouts,
    EpochLedger,
    OperatorStats,
    TreasuryConfig,
    D,
)
from swarmvision.routing.router import get_router, JobStatus


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="SwarmVision OS",
    description="Sovereign Distributed Compute Coordination",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class HeartbeatRequest(BaseModel):
    agent_ens: str
    timestamp: str
    hardware: dict
    uptime: Optional[float] = None
    jobs_completed: Optional[int] = None


class HeartbeatResponse(BaseModel):
    status: str
    agent_ens: str
    registered: bool


class JobSubmitRequest(BaseModel):
    client_ens: str
    model_id: str
    payload: Optional[dict] = None


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    client_ens: str
    model_id: str
    cost: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    client_ens: str
    model_id: str
    assigned_to: Optional[str]
    submitted_at: str
    completed_at: Optional[str]


class ProofSubmitRequest(BaseModel):
    """Legacy v0.1 proof format."""
    agent_ens: str
    job_id: str
    hardware: dict
    model_id: str
    start_time: str
    end_time: str
    result_hash: str
    signature: str


class ProofSubmitResponse(BaseModel):
    status: str
    job_id: str
    verified: bool
    payment: Optional[int]


class PoESubmitResponse(BaseModel):
    """v0.2 PoE response."""
    status: str
    poe_id: str
    job_id: str
    verified: bool
    payment: Optional[int]
    reputation_score: Optional[float]
    error: Optional[str] = None


class AccountResponse(BaseModel):
    ens_name: str
    balance: int
    total_earned: int
    total_spent: int
    jobs_submitted: int
    jobs_completed: int


# =============================================================================
# AGENT ENDPOINTS
# =============================================================================

@app.post("/agent/heartbeat", response_model=HeartbeatResponse)
async def agent_heartbeat(request: HeartbeatRequest):
    """
    Receive agent heartbeat.

    Agents send heartbeats every 30 seconds with:
    - Hardware capabilities
    - Uptime and job stats
    """
    router = get_router()
    treasury = get_treasury()

    # Register/update agent
    agent = router.register_agent(request.agent_ens, request.hardware)

    # v0.2: Record heartbeat for uptime tracking
    vram_gb = request.hardware.get("vram_total_gb", 0)
    gpu_count = request.hardware.get("gpu_count", 0)
    treasury.record_operator_heartbeat(request.agent_ens, vram_gb, gpu_count)

    return HeartbeatResponse(
        status="ok",
        agent_ens=request.agent_ens,
        registered=True,
    )


@app.get("/agent/jobs")
async def get_agent_jobs(agent_ens: str = Query(...)):
    """
    Poll for jobs.

    Agent polls this endpoint to receive work.
    """
    router = get_router()

    # Verify agent is registered
    agents = router.get_online_agents()
    if not any(a.ens_name == agent_ens for a in agents):
        # Auto-register on first poll
        router.register_agent(agent_ens, {})

    # Get next job for this agent
    job = router.get_next_job_for_agent(agent_ens)

    if job:
        return {
            "job": {
                "job_id": job.job_id,
                "model_id": job.model_id,
                "payload": job.payload,
                "client_ens": job.client_ens,
                "submitted_at": job.submitted_at,
            }
        }
    else:
        return {"job": None}


@app.get("/agents")
async def list_agents():
    """List all registered agents."""
    router = get_router()
    agents = router.get_online_agents()

    return {
        "agents": [
            {
                "ens_name": a.ens_name,
                "online": a.is_online,
                "gpu_count": a.gpu_count,
                "vram_gb": a.vram_gb,
                "jobs_completed": a.jobs_completed,
                "current_jobs": a.current_jobs,
            }
            for a in agents
        ],
        "total": len(agents),
    }


# =============================================================================
# JOB ENDPOINTS
# =============================================================================

@app.post("/job/submit", response_model=JobSubmitResponse)
async def submit_job(request: JobSubmitRequest):
    """
    Submit a job for execution.

    Requires sufficient credit balance.
    """
    treasury = get_treasury()
    router = get_router()

    # Check balance
    if not treasury.can_submit_job(request.client_ens):
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient balance. Required: {JOB_COST} credits"
        )

    # Reserve payment
    tx = treasury.reserve_job_payment(request.client_ens, "pending")
    if not tx:
        raise HTTPException(status_code=402, detail="Payment failed")

    # Submit job
    job = router.submit_job(
        client_ens=request.client_ens,
        model_id=request.model_id,
        payload=request.payload,
    )

    return JobSubmitResponse(
        job_id=job.job_id,
        status=job.status.value,
        client_ens=job.client_ens,
        model_id=job.model_id,
        cost=JOB_COST,
    )


@app.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get job status."""
    router = get_router()
    job = router.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        client_ens=job.client_ens,
        model_id=job.model_id,
        assigned_to=job.assigned_to,
        submitted_at=job.submitted_at,
        completed_at=job.completed_at,
    )


@app.get("/jobs")
async def list_jobs(
    client_ens: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=100)
):
    """List jobs with optional filters."""
    router = get_router()

    # Get all jobs (inefficient but OK for MVP)
    all_jobs = list(router._jobs.values())

    # Filter
    if client_ens:
        all_jobs = [j for j in all_jobs if j.client_ens == client_ens]
    if status:
        all_jobs = [j for j in all_jobs if j.status.value == status]

    # Sort by submission time (newest first)
    all_jobs.sort(key=lambda j: j.submitted_at, reverse=True)

    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status.value,
                "client_ens": j.client_ens,
                "model_id": j.model_id,
                "assigned_to": j.assigned_to,
                "submitted_at": j.submitted_at,
            }
            for j in all_jobs[:limit]
        ],
        "total": len(all_jobs),
    }


# =============================================================================
# PROOF ENDPOINTS
# =============================================================================

@app.post("/proof/submit", response_model=ProofSubmitResponse)
async def submit_proof(request: ProofSubmitRequest):
    """
    Submit proof of execution (legacy v0.1 format).

    Use /poe/submit for v0.2 format.
    """
    router = get_router()
    treasury = get_treasury()
    identity_service = get_identity_service()

    # Get job
    job = router.get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify job was assigned to this agent
    if job.assigned_to != request.agent_ens:
        raise HTTPException(status_code=403, detail="Job not assigned to this agent")

    # Get agent's registered address for signature verification
    identity = identity_service.resolve(request.agent_ens)
    if not identity:
        raise HTTPException(status_code=403, detail="Agent not registered")

    # Build proof data for verification (excluding signature)
    proof_data = {
        "agent_ens": request.agent_ens,
        "job_id": request.job_id,
        "hardware": request.hardware,
        "model_id": request.model_id,
        "start_time": request.start_time,
        "end_time": request.end_time,
        "result_hash": request.result_hash,
    }

    # Verify signature cryptographically
    verified = verify_proof_signature(
        proof_data=proof_data,
        signature=request.signature,
        address=identity.address,
    )

    # Fallback: also accept legacy placeholder signatures for backwards compat
    if not verified:
        verified = request.signature.startswith("sig:") or (
            request.signature.startswith("0x") and len(request.signature) == 132
        )

    if not verified:
        router.fail_job(request.job_id)
        return ProofSubmitResponse(
            status="rejected",
            job_id=request.job_id,
            verified=False,
            payment=None,
        )

    # Complete job
    router.complete_job(request.job_id, request.result_hash)

    # Pay operator
    tx = treasury.pay_operator(request.agent_ens, request.job_id)

    return ProofSubmitResponse(
        status="accepted",
        job_id=request.job_id,
        verified=True,
        payment=tx.amount,
    )


@app.post("/poe/submit", response_model=PoESubmitResponse)
async def submit_poe(poe: dict):
    """
    Submit Proof of Execution (v0.2 format).

    Validates PoE according to locked signing rule:
    1. Remove signature block
    2. Canonicalize: UTF-8, sorted keys, no whitespace
    3. message_hash = sha256(canonical_json)
    4. Verify signature against operator wallet

    No valid proof = no payout.
    """
    router = get_router()
    treasury = get_treasury()

    # Validate PoE
    result = validate_poe(poe)

    poe_id = poe.get("poe_id", "")
    job_id = poe.get("job", {}).get("job_id", "")
    operator_ens = poe.get("operator", {}).get("operator_ens", "")

    if not result.valid:
        # Record rejected proof (damages reputation)
        if operator_ens:
            treasury.record_rejected_poe(operator_ens)

        return PoESubmitResponse(
            status="rejected",
            poe_id=poe_id,
            job_id=job_id,
            verified=False,
            payment=None,
            reputation_score=None,
            error=result.error,
        )

    # Extract metrics from validated PoE
    metrics = extract_poe_metrics(poe)

    # Complete job in router
    job = router.get_job(job_id)
    if job:
        router.complete_job(job_id, poe.get("result", {}).get("result_hash", ""))

    # Process validated PoE - pay operator + update reputation
    tx = treasury.process_validated_poe(
        operator_ens=metrics["operator_ens"],
        job_id=metrics["job_id"],
        duration_ms=metrics["duration_ms"],
        result_status=metrics["result_status"],
        gpu_count=metrics["gpu_count"],
        vram_bytes=metrics["vram_bytes"],
    )

    # Get updated reputation score
    rep = treasury.get_operator_reputation(operator_ens)
    rep_score = rep["reputation_score"] if rep else 0.0

    return PoESubmitResponse(
        status="accepted",
        poe_id=poe_id,
        job_id=job_id,
        verified=True,
        payment=tx.amount,
        reputation_score=rep_score,
    )


@app.get("/reputation/{operator_ens}")
async def get_reputation(operator_ens: str):
    """Get operator reputation derived from validated PoEs."""
    treasury = get_treasury()
    rep = treasury.get_operator_reputation(operator_ens)

    if not rep:
        raise HTTPException(status_code=404, detail="No reputation data")

    return rep


@app.get("/reputation")
async def get_leaderboard(limit: int = Query(default=20, le=100)):
    """Get reputation leaderboard."""
    treasury = get_treasury()
    return {"leaderboard": treasury.get_reputation_leaderboard(limit)}


# =============================================================================
# ACCOUNT ENDPOINTS
# =============================================================================

@app.get("/account/{ens_name}", response_model=AccountResponse)
async def get_account(ens_name: str):
    """Get account balance and stats."""
    treasury = get_treasury()
    summary = treasury.get_account_summary(ens_name)

    return AccountResponse(**summary)


@app.post("/account/{ens_name}/deposit")
async def deposit_credits(ens_name: str, amount: int = Query(..., gt=0)):
    """
    Deposit credits to account.

    In production, this would be triggered by on-chain payment.
    For testing, accepts direct deposits.
    """
    treasury = get_treasury()
    tx = treasury.deposit(ens_name, amount)

    return {
        "status": "ok",
        "tx_id": tx.tx_id,
        "amount": amount,
        "balance": tx.balance_after,
    }


@app.get("/account/{ens_name}/transactions")
async def get_transactions(ens_name: str, limit: int = Query(default=50, le=100)):
    """Get account transaction history."""
    treasury = get_treasury()
    txs = treasury.get_transactions(ens_name, limit)

    return {
        "transactions": [
            {
                "tx_id": t.tx_id,
                "timestamp": t.timestamp,
                "type": t.tx_type.value,
                "amount": t.amount,
                "balance_after": t.balance_after,
                "reference": t.reference,
            }
            for t in txs
        ]
    }


# =============================================================================
# EPOCH ENDPOINTS
# =============================================================================

class EpochState:
    """Tracks current epoch for distribution."""
    def __init__(self):
        self.epoch_id = 0
        self.epoch_start = datetime.now(timezone.utc)
        self.gross_revenue = D("0")
        self.refunds = D("0")
        self.job_records: list[dict] = []

    def record_job(self, job_id: str, client_ens: str, operator_ens: str, amount: int):
        """Record a completed job for this epoch."""
        self.gross_revenue += D(amount)
        self.job_records.append({
            "job_id": job_id,
            "client_ens": client_ens,
            "operator_ens": operator_ens,
            "amount": amount,
        })

    def record_refund(self, amount: int):
        """Record a refund for this epoch."""
        self.refunds += D(amount)

    def reset(self):
        """Reset for next epoch."""
        self.epoch_id += 1
        self.epoch_start = datetime.now(timezone.utc)
        self.gross_revenue = D("0")
        self.refunds = D("0")
        self.job_records = []


_epoch_state = EpochState()


def get_epoch_state() -> EpochState:
    return _epoch_state


@app.post("/epoch/close")
async def close_epoch():
    """
    Close current epoch and compute payouts.

    Gathers operator stats and revenue, runs distribution algorithm,
    applies payouts to operator accounts.

    Returns signed PayoutReport.
    """
    treasury = get_treasury()
    epoch = get_epoch_state()

    # Build epoch ledger
    ledger = EpochLedger(
        gross_revenue=epoch.gross_revenue,
        refunds=epoch.refunds,
    )

    # Gather operator stats from treasury uptime tracking
    operators: list[OperatorStats] = []

    for ens, uptime in treasury._operator_uptime.items():
        # Get reputation data for job counts
        rep = treasury._operator_reputation.get(ens)

        operators.append(OperatorStats(
            operator_ens=ens,
            status="active" if uptime.is_online else "inactive",
            uptime_seconds=int(uptime.epoch_online_seconds),
            ready_seconds=int(uptime.epoch_online_seconds) if uptime.is_ready else 0,
            jobs_success=rep.total_jobs_success if rep else 0,
            jobs_failure=rep.total_jobs_failed if rep else 0,
            poe_invalid=rep.proofs_rejected if rep else 0,
        ))

    # Compute payouts
    cfg = TreasuryConfig()
    report = compute_epoch_payouts(ledger, operators, cfg)

    # Apply payouts to operator accounts
    for payout in report.payouts:
        if payout.payout > D("0"):
            treasury.deposit(
                payout.operator_ens,
                int(payout.payout),
                reference=f"epoch:{epoch.epoch_id}:distribution"
            )

    # Build response
    result = {
        "epoch_id": epoch.epoch_id,
        "epoch_start": epoch.epoch_start.isoformat(),
        "epoch_end": datetime.now(timezone.utc).isoformat(),
        "gross_revenue": str(report.gross_revenue),
        "protocol_fee": str(report.protocol_fee),
        "refunds": str(report.refunds),
        "net_pool": str(report.net_pool),
        "work_pool": str(report.work_pool),
        "readiness_pool": str(report.readiness_pool),
        "dust_rolled": str(report.dust_rolled),
        "payouts": [
            {
                "operator_ens": p.operator_ens,
                "eligible": p.eligible,
                "work_score": str(p.work_score),
                "readiness_score": str(p.readiness_score),
                "penalty": str(p.penalty),
                "payout": str(p.payout),
            }
            for p in report.payouts
        ],
        "operators_paid": len([p for p in report.payouts if p.payout > D("0")]),
        "total_distributed": str(sum(p.payout for p in report.payouts)),
    }

    # Reset epoch state for next period
    epoch.reset()

    return result


@app.get("/epoch/status")
async def epoch_status():
    """Get current epoch status."""
    epoch = get_epoch_state()
    treasury = get_treasury()

    return {
        "epoch_id": epoch.epoch_id,
        "epoch_start": epoch.epoch_start.isoformat(),
        "duration_seconds": (datetime.now(timezone.utc) - epoch.epoch_start).total_seconds(),
        "gross_revenue": str(epoch.gross_revenue),
        "refunds": str(epoch.refunds),
        "jobs_this_epoch": len(epoch.job_records),
        "operators_online": len(treasury.get_online_operators()),
    }


# =============================================================================
# STATUS ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "SwarmVision OS",
        "version": "0.1.0",
        "status": "operational",
    }


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


@app.get("/stats")
async def stats():
    """Get system statistics."""
    router = get_router()
    treasury = get_treasury()

    return {
        "routing": router.get_stats(),
        "treasury": treasury.get_protocol_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/readiness")
async def readiness_status():
    """
    Get readiness pool status (v0.2).

    Shows:
    - Current pool balance
    - Time to next distribution
    - Operator uptime rankings
    """
    treasury = get_treasury()
    return treasury.get_readiness_status()


@app.post("/readiness/distribute")
async def force_distribution():
    """
    Force immediate readiness distribution (admin endpoint).

    For testing and emergency distributions.
    """
    treasury = get_treasury()
    return treasury.force_readiness_distribution()


# =============================================================================
# RUN
# =============================================================================

def main():
    """Run the SwarmVision OS server."""
    import uvicorn

    print()
    print("=" * 50)
    print("SwarmVision OS Starting")
    print("Sovereign Distributed Compute")
    print("=" * 50)
    print()

    uvicorn.run(
        "swarmvision.os.core:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
