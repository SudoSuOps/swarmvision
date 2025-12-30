"""
SwarmVision Protocol — Job Router

The router assigns jobs to available agents based on:
- Agent capabilities (GPU, VRAM, etc.)
- Agent availability (last heartbeat)
- Job requirements (model, resources)
- Load balancing (round-robin, least-loaded)

This is the "scheduling" layer of SwarmVision OS.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Optional
import uuid


# =============================================================================
# CONSTANTS
# =============================================================================

# Agent considered offline after this many seconds without heartbeat
AGENT_TIMEOUT = 90  # 3 missed heartbeats at 30s interval

# Maximum jobs per agent in queue
MAX_AGENT_QUEUE = 5


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class JobStatus(Enum):
    """Job lifecycle status."""
    PENDING = "pending"      # Waiting for assignment
    ASSIGNED = "assigned"    # Assigned to agent
    RUNNING = "running"      # Agent executing
    COMPLETED = "completed"  # Proof submitted
    FAILED = "failed"        # Execution failed
    CANCELLED = "cancelled"  # Cancelled by client


@dataclass
class AgentInfo:
    """Information about a registered agent."""
    ens_name: str
    last_heartbeat: float = 0.0  # Unix timestamp
    gpu_count: int = 0
    gpu_names: list[str] = field(default_factory=list)
    vram_gb: float = 0.0
    cpu_cores: int = 0
    ram_gb: float = 0.0
    jobs_completed: int = 0
    current_jobs: int = 0

    @property
    def is_online(self) -> bool:
        """Check if agent is online (recent heartbeat)."""
        return (time.time() - self.last_heartbeat) < AGENT_TIMEOUT

    @property
    def can_accept_jobs(self) -> bool:
        """Check if agent can accept more jobs."""
        return self.is_online and self.current_jobs < MAX_AGENT_QUEUE


@dataclass
class Job:
    """A job in the system."""
    job_id: str
    client_ens: str
    model_id: str
    payload: dict
    status: JobStatus = JobStatus.PENDING
    submitted_at: str = ""
    assigned_to: Optional[str] = None
    assigned_at: Optional[str] = None
    completed_at: Optional[str] = None
    proof_hash: Optional[str] = None

    def __post_init__(self):
        if not self.submitted_at:
            self.submitted_at = datetime.now(timezone.utc).isoformat()


# =============================================================================
# ROUTER
# =============================================================================

class JobRouter:
    """
    Routes jobs to available agents.

    Strategies:
    - Round-robin: Distribute evenly across agents
    - Capability match: Match job requirements to agent capabilities
    - Least-loaded: Send to agent with fewest pending jobs
    """

    def __init__(self):
        self._agents: dict[str, AgentInfo] = {}
        self._jobs: dict[str, Job] = {}
        self._job_queue: list[str] = []  # Job IDs in order
        self._lock = Lock()
        self._round_robin_index = 0

    # =========================================================================
    # AGENT MANAGEMENT
    # =========================================================================

    def register_agent(self, ens_name: str, hardware: dict) -> AgentInfo:
        """Register or update an agent."""
        with self._lock:
            if ens_name in self._agents:
                agent = self._agents[ens_name]
            else:
                agent = AgentInfo(ens_name=ens_name)
                self._agents[ens_name] = agent

            # Update hardware info
            agent.gpu_count = hardware.get("gpu_count", 0)
            agent.gpu_names = hardware.get("gpu_names", [])
            agent.vram_gb = hardware.get("vram_gb", 0.0)
            agent.cpu_cores = hardware.get("cpu_cores", 0)
            agent.ram_gb = hardware.get("ram_gb", 0.0)
            agent.last_heartbeat = time.time()

            return agent

    def heartbeat(self, ens_name: str, hardware: Optional[dict] = None) -> bool:
        """Process agent heartbeat."""
        with self._lock:
            if ens_name not in self._agents:
                if hardware:
                    self.register_agent(ens_name, hardware)
                    return True
                return False

            agent = self._agents[ens_name]
            agent.last_heartbeat = time.time()

            if hardware:
                agent.gpu_count = hardware.get("gpu_count", agent.gpu_count)
                agent.vram_gb = hardware.get("vram_gb", agent.vram_gb)

            return True

    def get_online_agents(self) -> list[AgentInfo]:
        """Get list of online agents."""
        with self._lock:
            return [a for a in self._agents.values() if a.is_online]

    def get_available_agents(self) -> list[AgentInfo]:
        """Get agents that can accept jobs."""
        with self._lock:
            return [a for a in self._agents.values() if a.can_accept_jobs]

    # =========================================================================
    # JOB MANAGEMENT
    # =========================================================================

    def submit_job(
        self,
        client_ens: str,
        model_id: str,
        payload: Optional[dict] = None
    ) -> Job:
        """Submit a new job."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        job = Job(
            job_id=job_id,
            client_ens=client_ens,
            model_id=model_id,
            payload=payload or {},
        )

        with self._lock:
            self._jobs[job_id] = job
            self._job_queue.append(job_id)

        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def get_pending_jobs(self) -> list[Job]:
        """Get all pending jobs."""
        with self._lock:
            return [
                self._jobs[jid]
                for jid in self._job_queue
                if self._jobs[jid].status == JobStatus.PENDING
            ]

    def get_next_job_for_agent(self, agent_ens: str) -> Optional[Job]:
        """
        Get next job for an agent.

        Uses round-robin with capability matching.
        """
        with self._lock:
            agent = self._agents.get(agent_ens)
            if not agent or not agent.can_accept_jobs:
                return None

            # Find a pending job
            for job_id in self._job_queue:
                job = self._jobs[job_id]
                if job.status != JobStatus.PENDING:
                    continue

                # TODO: Check capability match
                # For now, any agent can take any job

                # Assign job
                job.status = JobStatus.ASSIGNED
                job.assigned_to = agent_ens
                job.assigned_at = datetime.now(timezone.utc).isoformat()
                agent.current_jobs += 1

                return job

            return None

    def assign_job(self, job_id: str, agent_ens: str) -> bool:
        """Manually assign a job to an agent."""
        with self._lock:
            job = self._jobs.get(job_id)
            agent = self._agents.get(agent_ens)

            if not job or not agent:
                return False

            if job.status != JobStatus.PENDING:
                return False

            if not agent.can_accept_jobs:
                return False

            job.status = JobStatus.ASSIGNED
            job.assigned_to = agent_ens
            job.assigned_at = datetime.now(timezone.utc).isoformat()
            agent.current_jobs += 1

            return True

    def complete_job(self, job_id: str, proof_hash: str) -> bool:
        """Mark job as completed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            if job.status not in (JobStatus.ASSIGNED, JobStatus.RUNNING):
                return False

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.proof_hash = proof_hash

            # Update agent stats
            if job.assigned_to and job.assigned_to in self._agents:
                agent = self._agents[job.assigned_to]
                agent.current_jobs = max(0, agent.current_jobs - 1)
                agent.jobs_completed += 1

            # Remove from queue
            if job_id in self._job_queue:
                self._job_queue.remove(job_id)

            return True

    def fail_job(self, job_id: str, reason: str = "") -> bool:
        """Mark job as failed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            job.status = JobStatus.FAILED

            # Update agent
            if job.assigned_to and job.assigned_to in self._agents:
                agent = self._agents[job.assigned_to]
                agent.current_jobs = max(0, agent.current_jobs - 1)

            # Remove from queue
            if job_id in self._job_queue:
                self._job_queue.remove(job_id)

            return True

    # =========================================================================
    # ROUTING STRATEGIES
    # =========================================================================

    def route_round_robin(self) -> Optional[tuple[Job, AgentInfo]]:
        """
        Route next pending job using round-robin.

        Returns (job, agent) tuple or None if nothing to route.
        """
        with self._lock:
            available = self.get_available_agents()
            if not available:
                return None

            pending = self.get_pending_jobs()
            if not pending:
                return None

            # Round-robin through agents
            job = pending[0]
            agent = available[self._round_robin_index % len(available)]
            self._round_robin_index += 1

            # Assign
            job.status = JobStatus.ASSIGNED
            job.assigned_to = agent.ens_name
            job.assigned_at = datetime.now(timezone.utc).isoformat()
            agent.current_jobs += 1

            return (job, agent)

    def route_capability_match(
        self,
        min_vram_gb: float = 0,
        min_gpu_count: int = 0
    ) -> Optional[tuple[Job, AgentInfo]]:
        """
        Route to agent matching capability requirements.
        """
        with self._lock:
            available = [
                a for a in self.get_available_agents()
                if a.vram_gb >= min_vram_gb and a.gpu_count >= min_gpu_count
            ]

            if not available:
                return None

            pending = self.get_pending_jobs()
            if not pending:
                return None

            # Pick least-loaded agent
            agent = min(available, key=lambda a: a.current_jobs)
            job = pending[0]

            job.status = JobStatus.ASSIGNED
            job.assigned_to = agent.ens_name
            job.assigned_at = datetime.now(timezone.utc).isoformat()
            agent.current_jobs += 1

            return (job, agent)

    # =========================================================================
    # STATS
    # =========================================================================

    def get_stats(self) -> dict:
        """Get routing statistics."""
        with self._lock:
            agents = list(self._agents.values())
            jobs = list(self._jobs.values())

            return {
                "total_agents": len(agents),
                "online_agents": len([a for a in agents if a.is_online]),
                "available_agents": len([a for a in agents if a.can_accept_jobs]),
                "total_jobs": len(jobs),
                "pending_jobs": len([j for j in jobs if j.status == JobStatus.PENDING]),
                "assigned_jobs": len([j for j in jobs if j.status == JobStatus.ASSIGNED]),
                "completed_jobs": len([j for j in jobs if j.status == JobStatus.COMPLETED]),
                "failed_jobs": len([j for j in jobs if j.status == JobStatus.FAILED]),
            }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_router: Optional[JobRouter] = None


def get_router() -> JobRouter:
    """Get the global router instance."""
    global _router
    if _router is None:
        _router = JobRouter()
    return _router
