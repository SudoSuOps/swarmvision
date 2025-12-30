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
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

# Import crypto module for real signatures
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from swarmvision.identity.crypto import sign_proof, verify_proof_signature, private_key_to_address
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


@dataclass
class GPUInfo:
    """Detailed GPU information."""
    index: int
    name: str
    vram_total_mb: int
    vram_used_mb: int
    vram_free_mb: int
    cuda_version: str
    driver_version: str
    power_draw_w: float
    power_limit_w: float
    temperature_c: int
    utilization_pct: int
    compute_capability: str


@dataclass
class HardwareSummary:
    """Hardware capabilities of the agent."""
    gpu_count: int
    gpu_names: list[str]
    vram_total_gb: float
    cpu_cores: int
    ram_gb: float
    # Extended GPU info (v0.2)
    gpus: Optional[list[dict]] = None
    cuda_version: Optional[str] = None
    driver_version: Optional[str] = None
    total_power_draw_w: Optional[float] = None
    total_power_limit_w: Optional[float] = None

    @classmethod
    def detect(cls) -> "HardwareSummary":
        """Detect hardware capabilities with detailed GPU parsing."""
        import subprocess

        # CPU info
        cpu_cores = os.cpu_count() or 1

        # RAM info (approximate)
        ram_gb = 0.0
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_kb = int(line.split()[1])
                        ram_gb = ram_kb / (1024 * 1024)
                        break
        except Exception:
            pass

        # GPU info - detailed nvidia-smi parsing
        gpu_count = 0
        gpu_names = []
        vram_total_gb = 0.0
        gpus = []
        cuda_version = None
        driver_version = None
        total_power_draw = 0.0
        total_power_limit = 0.0

        try:
            # Get CUDA and driver version
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                driver_version = result.stdout.strip().split("\n")[0]

            # Get CUDA version from nvidia-smi header
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "CUDA Version:" in line:
                        parts = line.split("CUDA Version:")
                        if len(parts) > 1:
                            cuda_version = parts[1].strip().split()[0]
                        break

            # Query detailed GPU info
            query_fields = [
                "index",
                "name",
                "memory.total",
                "memory.used",
                "memory.free",
                "power.draw",
                "power.limit",
                "temperature.gpu",
                "utilization.gpu",
                "compute_cap",
            ]
            result = subprocess.run(
                ["nvidia-smi", f"--query-gpu={','.join(query_fields)}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue

                    parts = [p.strip() for p in line.split(", ")]
                    if len(parts) < 10:
                        continue

                    try:
                        gpu_info = {
                            "index": int(parts[0]),
                            "name": parts[1],
                            "vram_total_mb": int(float(parts[2])),
                            "vram_used_mb": int(float(parts[3])),
                            "vram_free_mb": int(float(parts[4])),
                            "power_draw_w": float(parts[5]) if parts[5] != "[N/A]" else 0.0,
                            "power_limit_w": float(parts[6]) if parts[6] != "[N/A]" else 0.0,
                            "temperature_c": int(float(parts[7])) if parts[7] != "[N/A]" else 0,
                            "utilization_pct": int(float(parts[8])) if parts[8] != "[N/A]" else 0,
                            "compute_capability": parts[9] if parts[9] != "[N/A]" else "unknown",
                        }

                        gpus.append(gpu_info)
                        gpu_names.append(gpu_info["name"])
                        vram_total_gb += gpu_info["vram_total_mb"] / 1024
                        total_power_draw += gpu_info["power_draw_w"]
                        total_power_limit += gpu_info["power_limit_w"]
                        gpu_count += 1
                    except (ValueError, IndexError):
                        # Fallback: just get name and memory
                        gpu_names.append(parts[1])
                        gpu_count += 1

        except FileNotFoundError:
            # nvidia-smi not available
            pass
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

        return cls(
            gpu_count=gpu_count,
            gpu_names=gpu_names,
            vram_total_gb=round(vram_total_gb, 2),
            cpu_cores=cpu_cores,
            ram_gb=round(ram_gb, 2),
            gpus=gpus if gpus else None,
            cuda_version=cuda_version,
            driver_version=driver_version,
            total_power_draw_w=round(total_power_draw, 1) if total_power_draw > 0 else None,
            total_power_limit_w=round(total_power_limit, 1) if total_power_limit > 0 else None,
        )

    def is_gpu_ready(self, min_vram_gb: float = 0) -> bool:
        """Check if GPU is ready for compute."""
        if self.gpu_count == 0:
            return False
        if self.vram_total_gb < min_vram_gb:
            return False
        return True

    def get_available_vram_gb(self) -> float:
        """Get total available (free) VRAM across all GPUs."""
        if not self.gpus:
            return 0.0
        return sum(g.get("vram_free_mb", 0) for g in self.gpus) / 1024


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

    def __init__(self, agent_ens: str, job_id: str, model_id: str, private_key: Optional[str] = None):
        self.agent_ens = agent_ens
        self.job_id = job_id
        self.model_id = model_id
        self.hardware = HardwareSummary.detect()
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.result_data: Optional[bytes] = None
        self.proof: Optional[ProofOfExecution] = None
        # Private key for signing (from env or passed)
        self.private_key = private_key or os.environ.get("SWARMAGENT_PRIVATE_KEY", "")

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

        # Build proof data (without signature)
        proof_data = {
            "agent_ens": self.agent_ens,
            "job_id": self.job_id,
            "hardware": asdict(self.hardware),
            "model_id": self.model_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "result_hash": result_hash,
        }

        # Sign the proof
        if HAS_CRYPTO and self.private_key:
            signature = sign_proof(proof_data, self.private_key)
        else:
            # Fallback placeholder signature
            proof_hash = hashlib.sha256(
                json.dumps(proof_data, sort_keys=True).encode()
            ).hexdigest()
            signature = f"0x{'0' * 128}{proof_hash[:2]}"

        # Build proof object
        self.proof = ProofOfExecution(
            agent_ens=self.agent_ens,
            job_id=self.job_id,
            hardware=self.hardware,
            model_id=self.model_id,
            start_time=self.start_time,
            end_time=self.end_time,
            result_hash=result_hash,
            signature=signature,
        )

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
