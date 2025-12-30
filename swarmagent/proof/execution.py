"""
SwarmVision Protocol — Proof of Execution

Proof of Execution is the core primitive of SwarmVision.
It proves that a specific agent executed a specific job on specific hardware.

Structure:
- agent_ens: The operator's ENS identity
- job_id: Unique job identifier
- hardware: GPU/VRAM/system summary
- model_id: The model or pipeline executed
- start_time: ISO8601 timestamp
- end_time: ISO8601 timestamp
- result_hash: SHA256 of output (or mock)
- signature: Agent's cryptographic signature (placeholder for now)
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class HardwareSummary:
    """Hardware capabilities of the agent."""
    gpu_count: int
    gpu_names: list[str]
    vram_total_gb: float
    cpu_cores: int
    ram_gb: float

    @classmethod
    def detect(cls) -> "HardwareSummary":
        """Detect hardware capabilities."""
        import os

        # CPU info
        cpu_cores = os.cpu_count() or 1

        # RAM info (approximate)
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_kb = int(line.split()[1])
                        ram_gb = ram_kb / (1024 * 1024)
                        break
                else:
                    ram_gb = 0.0
        except:
            ram_gb = 0.0

        # GPU info
        gpu_count = 0
        gpu_names = []
        vram_total_gb = 0.0

        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split(", ")
                        gpu_names.append(parts[0].strip())
                        vram_total_gb += float(parts[1]) / 1024  # MB to GB
                        gpu_count += 1
        except:
            pass

        return cls(
            gpu_count=gpu_count,
            gpu_names=gpu_names,
            vram_total_gb=round(vram_total_gb, 2),
            cpu_cores=cpu_cores,
            ram_gb=round(ram_gb, 2)
        )


@dataclass
class ProofOfExecution:
    """
    Proof of Execution — the atomic unit of verified compute.

    This structure is signed by the agent and verified by SwarmVision OS.
    """
    agent_ens: str
    job_id: str
    hardware: HardwareSummary
    model_id: str
    start_time: str  # ISO8601
    end_time: str    # ISO8601
    result_hash: str
    signature: str   # Placeholder — will be ECDSA over proof hash

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "agent_ens": self.agent_ens,
            "job_id": self.job_id,
            "hardware": asdict(self.hardware),
            "model_id": self.model_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "result_hash": self.result_hash,
            "signature": self.signature,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    def proof_hash(self) -> str:
        """
        Compute the hash of the proof (excluding signature).
        This is what gets signed.
        """
        data = {
            "agent_ens": self.agent_ens,
            "job_id": self.job_id,
            "hardware": asdict(self.hardware),
            "model_id": self.model_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "result_hash": self.result_hash,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class ExecutionContext:
    """
    Context manager for tracked execution.

    Usage:
        with ExecutionContext(agent_ens, job_id, model_id) as ctx:
            # do work
            ctx.set_result(output_data)
        proof = ctx.proof
    """

    def __init__(self, agent_ens: str, job_id: str, model_id: str):
        self.agent_ens = agent_ens
        self.job_id = job_id
        self.model_id = model_id
        self.hardware = HardwareSummary.detect()
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.result_data: Optional[bytes] = None
        self.proof: Optional[ProofOfExecution] = None

    def __enter__(self):
        self.start_time = datetime.now(timezone.utc).isoformat()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = datetime.now(timezone.utc).isoformat()

        # Compute result hash
        if self.result_data:
            result_hash = hashlib.sha256(self.result_data).hexdigest()
        else:
            # Mock result for stub executions
            result_hash = hashlib.sha256(f"mock:{self.job_id}".encode()).hexdigest()

        # Build proof
        self.proof = ProofOfExecution(
            agent_ens=self.agent_ens,
            job_id=self.job_id,
            hardware=self.hardware,
            model_id=self.model_id,
            start_time=self.start_time,
            end_time=self.end_time,
            result_hash=result_hash,
            signature="SIGNATURE_PLACEHOLDER",  # TODO: Real ECDSA signing
        )

        # Sign the proof (placeholder)
        # In production: signature = sign(proof.proof_hash(), private_key)
        self.proof.signature = f"sig:{self.proof.proof_hash()[:16]}"

        return False  # Don't suppress exceptions

    def set_result(self, data: bytes):
        """Set the result data for hashing."""
        self.result_data = data


def create_proof(
    agent_ens: str,
    job_id: str,
    model_id: str,
    result_data: Optional[bytes] = None,
    execution_time_ms: int = 100
) -> ProofOfExecution:
    """
    Create a Proof of Execution.

    This is a convenience function for simple cases.
    For real execution, use ExecutionContext.
    """
    hardware = HardwareSummary.detect()
    start = datetime.now(timezone.utc)

    # Simulate execution time
    time.sleep(execution_time_ms / 1000)

    end = datetime.now(timezone.utc)

    if result_data:
        result_hash = hashlib.sha256(result_data).hexdigest()
    else:
        result_hash = hashlib.sha256(f"mock:{job_id}".encode()).hexdigest()

    proof = ProofOfExecution(
        agent_ens=agent_ens,
        job_id=job_id,
        hardware=hardware,
        model_id=model_id,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        result_hash=result_hash,
        signature="SIGNATURE_PLACEHOLDER",
    )

    # Placeholder signature
    proof.signature = f"sig:{proof.proof_hash()[:16]}"

    return proof


# =============================================================================
# VERIFICATION (SwarmVision OS uses this)
# =============================================================================

def verify_proof(proof: ProofOfExecution) -> bool:
    """
    Verify a Proof of Execution.

    Currently a stub — in production this would:
    1. Verify the signature against the agent's public key
    2. Check that the agent is registered
    3. Validate timestamps are reasonable
    4. Verify hardware matches known agent capabilities
    """
    # Stub: Just check signature format
    if not proof.signature.startswith("sig:"):
        return False

    # Check timestamps are valid ISO8601
    try:
        datetime.fromisoformat(proof.start_time.replace("Z", "+00:00"))
        datetime.fromisoformat(proof.end_time.replace("Z", "+00:00"))
    except:
        return False

    # Check required fields
    if not all([proof.agent_ens, proof.job_id, proof.model_id, proof.result_hash]):
        return False

    return True
