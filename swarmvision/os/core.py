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
    TreasuryConfig,
    D,
)
from swarmvision.treasury.state import (
    TreasuryEpochState,
    current_epoch_window,
)
from swarmvision.treasury.report_signing import sign_payout_report
from swarmvision.identity.signing import canonical_json_bytes, sha256_hex
from swarmvision.identity.ethsig import recover_eip191_address
from swarmvision.identity.ens import is_valid_operator_ens
from swarmvision.routing.router import get_router, JobStatus
import os

# Protocol signing key (for signing payout reports)
PROTOCOL_SIGNER_KEY = os.environ.get("SWARMVISION_SIGNING_KEY", "")


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


# PoE v0.2 structured models
class PoESignature(BaseModel):
    scheme: str
    message_hash: str
    signature: str


class PoEOperatorWallet(BaseModel):
    chain: str
    address: str


class PoEOperator(BaseModel):
    operator_ens: str
    wallet: PoEOperatorWallet
    agent: dict


class PoEJobPricing(BaseModel):
    currency: str
    unit_price: str
    unit: str


class PoEJob(BaseModel):
    job_id: str
    client_ens: str
    task: str
    received_at: str
    pricing: PoEJobPricing


class PoEResult(BaseModel):
    status: str
    result_hash: str


class PoEArtifact(BaseModel):
    artifact_id: str
    type: str
    hash: str


class PoEExecution(BaseModel):
    started_at: str
    ended_at: str
    duration_ms: int
    host: dict
    resources: dict


class ProofOfExecution(BaseModel):
    protocol: dict
    poe_id: str
    job: PoEJob
    operator: PoEOperator
    execution: PoEExecution
    artifact: PoEArtifact
    result: PoEResult
    attestations: dict
    signature: PoESignature


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
    epoch = get_epoch_state()

    # Register/update agent
    agent = router.register_agent(request.agent_ens, request.hardware)

    # v0.2: Record heartbeat for uptime tracking (legacy treasury pool)
    vram_gb = request.hardware.get("vram_total_gb", 0)
    gpu_count = request.hardware.get("gpu_count", 0)
    treasury.record_operator_heartbeat(request.agent_ens, vram_gb, gpu_count)

    # v0.2: Record heartbeat to epoch state (new distribution system)
    # Standard heartbeat interval is 30 seconds
    HEARTBEAT_INTERVAL = 30
    epoch.record_heartbeat(
        operator_ens=request.agent_ens,
        uptime_delta=HEARTBEAT_INTERVAL,
        ready_delta=HEARTBEAT_INTERVAL,
        status="active",
    )

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
# JOB RESULT STORAGE
# =============================================================================

# In-memory result and PoE storage (would be persistent in production)
_job_results: dict[str, bytes] = {}
_job_poes: dict[str, dict] = {}


class JobResultUpload(BaseModel):
    job_id: str
    data: str  # base64 encoded
    content_type: str = "application/octet-stream"


@app.post("/job/{job_id}/result")
async def upload_job_result(job_id: str, upload: JobResultUpload):
    """
    Upload job result artifact.

    Called by SwarmAgent after job execution.
    """
    import base64

    router = get_router()
    job = router.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Decode and store
    try:
        result_data = base64.b64decode(upload.data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 data")

    _job_results[job_id] = result_data

    return {
        "status": "ok",
        "job_id": job_id,
        "size": len(result_data),
        "content_type": upload.content_type,
    }


@app.get("/job/{job_id}/result")
async def download_job_result(job_id: str):
    """
    Download job result artifact.

    Called by client to retrieve completed job output.
    """
    from fastapi.responses import Response

    router = get_router()
    job = router.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job_id not in _job_results:
        raise HTTPException(status_code=404, detail="Result not available")

    return Response(
        content=_job_results[job_id],
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={job_id}.pdf"}
    )


@app.get("/job/{job_id}/poe")
async def get_job_poe(job_id: str):
    """
    Get Proof of Execution for a job.

    Returns the PoE that was submitted for this job.
    """
    if job_id not in _job_poes:
        raise HTTPException(status_code=404, detail="PoE not found for job")

    return _job_poes[job_id]


def store_poe(job_id: str, poe: dict):
    """Store PoE for later retrieval."""
    _job_poes[job_id] = poe


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


def _is_client_ens(x: str) -> bool:
    return x.endswith(".swarmvision.eth")


def _is_operator_ens(x: str) -> bool:
    return x.endswith(".swarmcompute.eth")


@app.post("/poe/submit")
async def submit_poe(poe: ProofOfExecution):
    """
    Submit Proof of Execution (v0.2 format).

    Validates PoE according to locked signing rule:
    1. Remove signature block
    2. Canonicalize: UTF-8, sorted keys, no whitespace
    3. message_hash = sha256(canonical_json)
    4. Verify signature against operator wallet

    No valid proof = no payout.
    """
    from decimal import Decimal

    epoch = get_epoch_state()
    treasury = get_treasury()

    # 1) Namespace checks
    if not _is_client_ens(poe.job.client_ens):
        raise HTTPException(400, "invalid client_ens namespace")
    if not _is_operator_ens(poe.operator.operator_ens):
        raise HTTPException(400, "invalid operator_ens namespace")

    # 2) Canonical signing rule: remove signature, hash
    poe_dict = poe.model_dump()
    sig_block = poe_dict.pop("signature", None)
    b = canonical_json_bytes(poe_dict)
    h = sha256_hex(b)

    if sig_block is None:
        raise HTTPException(400, "missing signature")

    if poe.signature.scheme != "eip191":
        raise HTTPException(400, "unsupported signature scheme (v0.2 supports eip191)")

    # 3) Verify message hash matches
    if poe.signature.message_hash != h:
        epoch.record_poe(poe.operator.operator_ens, success=False, poe_valid=False)
        raise HTTPException(400, "message_hash mismatch")

    # 4) Recover signer and verify
    try:
        recovered = recover_eip191_address(h, poe.signature.signature)
    except Exception:
        epoch.record_poe(poe.operator.operator_ens, success=False, poe_valid=False)
        raise HTTPException(401, "invalid signature")

    claimed = poe.operator.wallet.address.lower()
    if recovered != claimed:
        epoch.record_poe(poe.operator.operator_ens, success=False, poe_valid=False)
        raise HTTPException(401, "signature does not match operator.wallet.address")

    # 5) ENS authorization check (verify wallet controls ENS)
    ens_service = get_identity_service()
    if not ens_service.verify_signature_authority(poe.operator.operator_ens, claimed):
        epoch.record_poe(poe.operator.operator_ens, success=False, poe_valid=False)
        raise HTTPException(401, "wallet not authorized for operator_ens")

    # 6) Accounting: revenue + stats
    unit_price = Decimal(poe.job.pricing.unit_price)
    epoch.record_job_charge(unit_price)

    success = (poe.result.status == "success")
    epoch.record_poe(poe.operator.operator_ens, success=success, poe_valid=True)

    # 6b) Grant uptime credit for valid PoE (execution duration as uptime)
    # This ensures operators accumulate uptime from work, not just heartbeats
    uptime_seconds = max(1, poe.execution.duration_ms // 1000)
    epoch.record_heartbeat(
        operator_ens=poe.operator.operator_ens,
        uptime_delta=uptime_seconds,
        ready_delta=uptime_seconds,
        status="active",
    )

    # 7) Process validated PoE in treasury
    tx = treasury.process_validated_poe(
        operator_ens=poe.operator.operator_ens,
        job_id=poe.job.job_id,
        duration_ms=poe.execution.duration_ms,
        result_status=poe.result.status,
        gpu_count=len(poe.execution.resources.get("gpus", [])),
        vram_bytes=sum(g.get("vram_bytes", 0) for g in poe.execution.resources.get("gpus", [])),
    )

    # Get updated reputation
    rep = treasury.get_operator_reputation(poe.operator.operator_ens)
    rep_score = rep["reputation_score"] if rep else 0.0

    # Store PoE for later retrieval by client
    store_poe(poe.job.job_id, poe.model_dump())

    return {
        "ok": True,
        "epoch_id": epoch.epoch_id,
        "poe_id": poe.poe_id,
        "job_id": poe.job.job_id,
        "message_hash": h,
        "verified": True,
        "payment": tx.amount,
        "reputation_score": rep_score,
    }


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

_epoch_state: TreasuryEpochState | None = None


def get_epoch_state() -> TreasuryEpochState:
    global _epoch_state
    if _epoch_state is None:
        start, end = current_epoch_window(86400)
        _epoch_state = TreasuryEpochState(
            epoch_id=f"epoch_{start}",
            epoch_start_ts=start,
            epoch_end_ts=end,
        )
    return _epoch_state


def reset_epoch_state() -> TreasuryEpochState:
    global _epoch_state
    start, end = current_epoch_window(86400)
    _epoch_state = TreasuryEpochState(
        epoch_id=f"epoch_{start}",
        epoch_start_ts=start,
        epoch_end_ts=end,
    )
    return _epoch_state


@app.post("/epoch/close")
async def close_epoch():
    """
    Close current epoch and compute payouts (unsigned).

    Use /treasury/epoch/close for signed reports.
    """
    treasury = get_treasury()
    epoch = get_epoch_state()

    # Build inputs from epoch state
    ledger = epoch.to_ledger()
    operators = epoch.to_operator_stats()

    # Compute payouts
    cfg = TreasuryConfig()
    report = compute_epoch_payouts(ledger, operators, cfg)

    # Apply payouts to operator accounts
    for payout in report.payouts:
        if payout.payout > D("0"):
            treasury.deposit(
                payout.operator_ens,
                int(payout.payout),
                reference=f"{epoch.epoch_id}:distribution"
            )

    # Build response
    result = {
        "epoch_id": epoch.epoch_id,
        "epoch_start_ts": epoch.epoch_start_ts,
        "epoch_end_ts": epoch.epoch_end_ts,
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
    reset_epoch_state()

    return result


@app.post("/treasury/epoch/close")
async def treasury_close_epoch():
    """
    Close current epoch and compute signed payout report.

    Requires SWARMVISION_SIGNING_KEY environment variable.
    Returns signed PayoutReport for auditability.
    """
    import time

    treasury = get_treasury()
    epoch = get_epoch_state()

    if not PROTOCOL_SIGNER_KEY:
        raise HTTPException(500, "SWARMVISION_SIGNING_KEY not set")

    # Build inputs from epoch state
    ledger = epoch.to_ledger()
    operators = epoch.to_operator_stats()

    # Compute payouts
    cfg = TreasuryConfig()
    report = compute_epoch_payouts(ledger, operators, cfg)

    # Sign the report
    signed = sign_payout_report(report, PROTOCOL_SIGNER_KEY)

    # Apply payouts to operator accounts
    for payout in report.payouts:
        if payout.payout > D("0"):
            treasury.deposit(
                payout.operator_ens,
                int(payout.payout),
                reference=f"{epoch.epoch_id}:distribution"
            )

    # Reset epoch state for next period
    reset_epoch_state()

    return signed


@app.get("/epoch/status")
async def epoch_status():
    """Get current epoch status."""
    epoch = get_epoch_state()
    treasury = get_treasury()
    import time

    return {
        "epoch_id": epoch.epoch_id,
        "epoch_start_ts": epoch.epoch_start_ts,
        "epoch_end_ts": epoch.epoch_end_ts,
        "seconds_remaining": max(0, epoch.epoch_end_ts - int(time.time())),
        "gross_revenue": str(epoch.gross_revenue),
        "refunds": str(epoch.refunds),
        "operators_tracked": len(epoch.operators),
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
