"""
SwarmVision Protocol — Proof of Execution Validation

Validates PoE according to the locked signing rule:
1. Remove signature block
2. Canonicalize: UTF-8, sorted keys, no whitespace
3. message_hash = sha256(canonical_json)
4. Verify signature against operator wallet

No valid proof, no payout.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

from .crypto import verify_signature
from .ens import get_identity_service, is_valid_operator_ens


@dataclass
class PoEValidationResult:
    """Result of PoE validation."""
    valid: bool
    error: Optional[str] = None
    operator_address: Optional[str] = None
    computed_hash: Optional[str] = None


def canonicalize(data: dict) -> bytes:
    """
    Canonicalize JSON for signing.

    Rules (LOCKED):
    - UTF-8 encoding
    - Sorted keys (recursive)
    - No whitespace
    - Separators: ',' and ':'
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")


def compute_message_hash(poe_without_signature: dict) -> str:
    """Compute sha256 of canonical PoE."""
    canonical = canonicalize(poe_without_signature)
    return hashlib.sha256(canonical).hexdigest()


def validate_poe(poe: dict) -> PoEValidationResult:
    """
    Validate a Proof of Execution.

    From ENS.resolution.md section 8:
    1. Wallet is authorized for operator_ens
    2. Signature matches PoE message hash
    3. ENS status was active at execution time

    Any check fails → PoE invalid.
    """
    # Check required top-level fields
    required = ["protocol", "poe_id", "job", "operator", "execution",
                "artifact", "result", "attestations", "signature"]
    for field in required:
        if field not in poe:
            return PoEValidationResult(valid=False, error=f"Missing field: {field}")

    # Check protocol
    if poe.get("protocol", {}).get("name") != "swarmvision":
        return PoEValidationResult(valid=False, error="Invalid protocol name")

    version = poe.get("protocol", {}).get("version", "")
    if not version.startswith("0."):
        return PoEValidationResult(valid=False, error="Invalid protocol version")

    # Check operator
    operator = poe.get("operator", {})
    operator_ens = operator.get("operator_ens", "")

    if not operator_ens:
        return PoEValidationResult(valid=False, error="Missing operator_ens")

    if not is_valid_operator_ens(operator_ens):
        return PoEValidationResult(valid=False, error="Invalid operator ENS pattern")

    if "wallet" not in operator:
        return PoEValidationResult(valid=False, error="Missing operator.wallet")

    wallet_address = operator.get("wallet", {}).get("address", "")
    if not wallet_address.startswith("0x") or len(wallet_address) != 42:
        return PoEValidationResult(valid=False, error="Invalid wallet address")

    # Verify wallet is authorized for operator_ens (from ENS.resolution.md section 8)
    ens_service = get_identity_service()
    if not ens_service.verify_signature_authority(operator_ens, wallet_address):
        return PoEValidationResult(
            valid=False,
            error="Wallet not authorized for operator_ens",
            operator_address=wallet_address
        )

    # Extract signature block
    signature_block = poe.get("signature", {})
    if not all(k in signature_block for k in ["scheme", "message_hash", "signature"]):
        return PoEValidationResult(valid=False, error="Incomplete signature block")

    claimed_hash = signature_block["message_hash"]
    signature = signature_block["signature"]
    scheme = signature_block["scheme"]

    if scheme not in ["eip191", "eip712"]:
        return PoEValidationResult(valid=False, error=f"Unsupported signature scheme: {scheme}")

    # Remove signature and canonicalize
    poe_copy = {k: v for k, v in poe.items() if k != "signature"}
    computed_hash = compute_message_hash(poe_copy)

    # Verify hash matches
    if computed_hash != claimed_hash:
        return PoEValidationResult(
            valid=False,
            error="Hash mismatch",
            computed_hash=computed_hash
        )

    # Verify signature
    if not verify_signature(computed_hash, signature, wallet_address):
        return PoEValidationResult(
            valid=False,
            error="Invalid signature",
            operator_address=wallet_address,
            computed_hash=computed_hash
        )

    return PoEValidationResult(
        valid=True,
        operator_address=wallet_address,
        computed_hash=computed_hash
    )


def extract_poe_metrics(poe: dict) -> dict:
    """
    Extract metrics from validated PoE for treasury/reputation.

    Returns dict with:
    - operator_ens
    - operator_address
    - job_id
    - task
    - duration_ms
    - gpu_count
    - vram_bytes
    - result_status
    - pricing
    """
    operator = poe.get("operator", {})
    job = poe.get("job", {})
    execution = poe.get("execution", {})
    result = poe.get("result", {})

    resources = execution.get("resources", {})
    gpus = resources.get("gpus", [])

    return {
        "operator_ens": operator.get("operator_ens", ""),
        "operator_address": operator.get("wallet", {}).get("address", ""),
        "job_id": job.get("job_id", ""),
        "client_ens": job.get("client_ens", ""),
        "task": job.get("task", ""),
        "duration_ms": execution.get("duration_ms", 0),
        "gpu_count": len(gpus),
        "vram_bytes": sum(g.get("vram_bytes", 0) for g in gpus),
        "result_status": result.get("status", ""),
        "pricing": job.get("pricing", {}),
    }
