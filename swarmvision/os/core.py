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
from swarmvision.treasury.pool import get_treasury, JOB_COST
from swarmvision.routing.router import get_router, JobStatus


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="SwarmVision OS",
    description="Sovereign Distributed Compute Coordination",
    version="0.1.0",
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

    # Register/update agent
    agent = router.register_agent(request.agent_ens, request.hardware)

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
    Submit proof of execution.

    Agent submits proof after completing a job.
    Triggers payment if valid.
    """
    router = get_router()
    treasury = get_treasury()

    # Get job
    job = router.get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify job was assigned to this agent
    if job.assigned_to != request.agent_ens:
        raise HTTPException(status_code=403, detail="Job not assigned to this agent")

    # Verify proof (stub - just check signature format)
    verified = request.signature.startswith("sig:")

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
