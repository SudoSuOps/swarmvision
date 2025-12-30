"""
SwarmVision Protocol — SwarmAgent Daemon

The SwarmAgent daemon is the core execution engine.
It:
1. Maintains identity via wallet/ENS
2. Sends heartbeats to SwarmVision OS
3. Reports hardware capabilities
4. Executes jobs and produces Proofs of Execution
5. Submits proofs for verification and payment

This is the "mining software" of SwarmVision.
"""

import asyncio
import json
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from swarmagent.proof.execution import (
    HardwareSummary,
    ProofOfExecution,
    ExecutionContext,
    create_proof,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AgentConfig:
    """SwarmAgent configuration."""

    # Identity
    ens_name: str = ""
    private_key: str = ""  # Hex string, no 0x prefix

    # SwarmVision OS connection
    coordinator_url: str = "http://localhost:8000"

    # Behavior
    heartbeat_interval: int = 30  # seconds
    job_poll_interval: int = 5   # seconds

    # Paths
    config_dir: Path = field(default_factory=lambda: Path.home() / ".swarmagent")
    proofs_dir: Path = field(default_factory=lambda: Path.home() / ".swarmagent" / "proofs")

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load configuration from environment variables."""
        return cls(
            ens_name=os.environ.get("SWARMAGENT_ENS", ""),
            private_key=os.environ.get("SWARMAGENT_PRIVATE_KEY", ""),
            coordinator_url=os.environ.get("SWARMVISION_URL", "http://localhost:8000"),
            heartbeat_interval=int(os.environ.get("SWARMAGENT_HEARTBEAT", "30")),
            job_poll_interval=int(os.environ.get("SWARMAGENT_POLL", "5")),
        )

    @classmethod
    def from_file(cls, path: Path) -> "AgentConfig":
        """Load configuration from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            ens_name=data.get("ens_name", ""),
            private_key=data.get("private_key", ""),
            coordinator_url=data.get("coordinator_url", "http://localhost:8000"),
            heartbeat_interval=data.get("heartbeat_interval", 30),
            job_poll_interval=data.get("job_poll_interval", 5),
        )

    def save(self, path: Optional[Path] = None):
        """Save configuration to file."""
        path = path or (self.config_dir / "config.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "ens_name": self.ens_name,
                "private_key": self.private_key,
                "coordinator_url": self.coordinator_url,
                "heartbeat_interval": self.heartbeat_interval,
                "job_poll_interval": self.job_poll_interval,
            }, f, indent=2)

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.ens_name:
            errors.append("ENS name is required (set SWARMAGENT_ENS)")
        if not self.ens_name.endswith(".eth"):
            errors.append("ENS name must end with .eth")
        return errors


# =============================================================================
# JOB HANDLING
# =============================================================================

@dataclass
class Job:
    """A job to be executed."""
    job_id: str
    model_id: str
    payload: dict
    submitted_at: str
    client_ens: str


class JobExecutor:
    """
    Executes jobs and produces proofs.

    This is a stub executor — real implementations would:
    - Load the specified model
    - Execute the pipeline
    - Return actual results
    """

    def __init__(self, agent_ens: str):
        self.agent_ens = agent_ens
        self.handlers: dict[str, Callable] = {}

        # Register default mock handler
        self.register_handler("*", self._mock_execute)

    def register_handler(self, model_id: str, handler: Callable):
        """Register a handler for a specific model."""
        self.handlers[model_id] = handler

    def execute(self, job: Job) -> ProofOfExecution:
        """Execute a job and return proof."""
        handler = self.handlers.get(job.model_id, self.handlers.get("*"))

        with ExecutionContext(self.agent_ens, job.job_id, job.model_id) as ctx:
            result = handler(job)
            if isinstance(result, bytes):
                ctx.set_result(result)
            elif isinstance(result, str):
                ctx.set_result(result.encode())
            else:
                ctx.set_result(json.dumps(result).encode())

        return ctx.proof

    def _mock_execute(self, job: Job) -> dict:
        """Mock execution — simulates work."""
        time.sleep(0.5)  # Simulate processing
        return {
            "status": "completed",
            "job_id": job.job_id,
            "model_id": job.model_id,
            "mock": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# =============================================================================
# AGENT DAEMON
# =============================================================================

class SwarmAgent:
    """
    The SwarmAgent daemon.

    Lifecycle:
    1. Initialize with config
    2. Connect to SwarmVision OS
    3. Start heartbeat loop
    4. Poll for jobs and execute
    5. Submit proofs
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.hardware = HardwareSummary.detect()
        self.executor = JobExecutor(config.ens_name)
        self.running = False
        self.start_time = datetime.now(timezone.utc)

        # Stats
        self.jobs_completed = 0
        self.proofs_submitted = 0
        self.last_heartbeat: Optional[datetime] = None

        # Ensure directories exist
        self.config.config_dir.mkdir(parents=True, exist_ok=True)
        self.config.proofs_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        """Get agent status."""
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return {
            "ens_name": self.config.ens_name,
            "coordinator": self.config.coordinator_url,
            "running": self.running,
            "uptime_seconds": int(uptime),
            "jobs_completed": self.jobs_completed,
            "proofs_submitted": self.proofs_submitted,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "hardware": {
                "gpu_count": self.hardware.gpu_count,
                "gpu_names": self.hardware.gpu_names,
                "vram_gb": self.hardware.vram_total_gb,
                "cpu_cores": self.hardware.cpu_cores,
                "ram_gb": self.hardware.ram_gb,
            },
        }

    async def heartbeat(self):
        """Send heartbeat to coordinator."""
        try:
            import aiohttp
        except ImportError:
            # Fallback to sync requests
            self._sync_heartbeat()
            return

        payload = {
            "agent_ens": self.config.ens_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hardware": {
                "gpu_count": self.hardware.gpu_count,
                "gpu_names": self.hardware.gpu_names,
                "vram_gb": self.hardware.vram_total_gb,
                "cpu_cores": self.hardware.cpu_cores,
                "ram_gb": self.hardware.ram_gb,
            },
            "uptime": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            "jobs_completed": self.jobs_completed,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.coordinator_url}/agent/heartbeat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        self.last_heartbeat = datetime.now(timezone.utc)
                        return True
        except Exception as e:
            print(f"[heartbeat] Failed: {e}")

        return False

    def _sync_heartbeat(self):
        """Synchronous heartbeat fallback."""
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "agent_ens": self.config.ens_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hardware": {
                "gpu_count": self.hardware.gpu_count,
                "gpu_names": self.hardware.gpu_names,
                "vram_gb": self.hardware.vram_total_gb,
                "cpu_cores": self.hardware.cpu_cores,
                "ram_gb": self.hardware.ram_gb,
            },
        }).encode()

        try:
            req = urllib.request.Request(
                f"{self.config.coordinator_url}/agent/heartbeat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self.last_heartbeat = datetime.now(timezone.utc)
                    return True
        except Exception as e:
            print(f"[heartbeat] Failed: {e}")

        return False

    async def poll_jobs(self) -> Optional[Job]:
        """Poll for available jobs."""
        try:
            import aiohttp
        except ImportError:
            return self._sync_poll_jobs()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.coordinator_url}/agent/jobs",
                    params={"agent_ens": self.config.ens_name},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("job"):
                            j = data["job"]
                            return Job(
                                job_id=j["job_id"],
                                model_id=j["model_id"],
                                payload=j.get("payload", {}),
                                submitted_at=j.get("submitted_at", ""),
                                client_ens=j.get("client_ens", ""),
                            )
        except Exception as e:
            print(f"[poll] Failed: {e}")

        return None

    def _sync_poll_jobs(self) -> Optional[Job]:
        """Synchronous job polling fallback."""
        import urllib.request
        import urllib.error

        try:
            url = f"{self.config.coordinator_url}/agent/jobs?agent_ens={self.config.ens_name}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read())
                    if data.get("job"):
                        j = data["job"]
                        return Job(
                            job_id=j["job_id"],
                            model_id=j["model_id"],
                            payload=j.get("payload", {}),
                            submitted_at=j.get("submitted_at", ""),
                            client_ens=j.get("client_ens", ""),
                        )
        except Exception as e:
            print(f"[poll] Failed: {e}")

        return None

    async def submit_proof(self, proof: ProofOfExecution) -> bool:
        """Submit proof to coordinator."""
        # Save locally first
        proof_path = self.config.proofs_dir / f"{proof.job_id}.json"
        with open(proof_path, "w") as f:
            f.write(proof.to_json())

        try:
            import aiohttp
        except ImportError:
            return self._sync_submit_proof(proof)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.coordinator_url}/proof/submit",
                    json=proof.to_dict(),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        self.proofs_submitted += 1
                        return True
        except Exception as e:
            print(f"[proof] Submit failed: {e}")

        return False

    def _sync_submit_proof(self, proof: ProofOfExecution) -> bool:
        """Synchronous proof submission fallback."""
        import urllib.request

        try:
            req = urllib.request.Request(
                f"{self.config.coordinator_url}/proof/submit",
                data=proof.to_json().encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self.proofs_submitted += 1
                    return True
        except Exception as e:
            print(f"[proof] Submit failed: {e}")

        return False

    async def run(self):
        """Main daemon loop."""
        self.running = True
        print(f"[agent] Starting SwarmAgent: {self.config.ens_name}")
        print(f"[agent] Hardware: {self.hardware.gpu_count} GPUs, {self.hardware.vram_total_gb}GB VRAM")
        print(f"[agent] Coordinator: {self.config.coordinator_url}")

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop)

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        job_task = asyncio.create_task(self._job_loop())

        try:
            await asyncio.gather(heartbeat_task, job_task)
        except asyncio.CancelledError:
            pass

        print("[agent] Stopped")

    async def _heartbeat_loop(self):
        """Heartbeat loop."""
        while self.running:
            await self.heartbeat()
            await asyncio.sleep(self.config.heartbeat_interval)

    async def _job_loop(self):
        """Job polling and execution loop."""
        while self.running:
            job = await self.poll_jobs()
            if job:
                print(f"[job] Received: {job.job_id} ({job.model_id})")
                proof = self.executor.execute(job)
                print(f"[job] Completed: {job.job_id}")
                await self.submit_proof(proof)
                self.jobs_completed += 1
            await asyncio.sleep(self.config.job_poll_interval)

    def stop(self):
        """Stop the daemon."""
        print("[agent] Stopping...")
        self.running = False

    def run_sync(self):
        """Run synchronously (blocking)."""
        asyncio.run(self.run())


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

def main():
    """Run agent from command line."""
    config = AgentConfig.from_env()
    errors = config.validate()

    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    agent = SwarmAgent(config)
    agent.run_sync()


if __name__ == "__main__":
    main()
