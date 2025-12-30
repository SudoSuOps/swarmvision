"""
SwarmVision Protocol — PoE Signing Utilities

Deterministic canonicalization and hashing for PoE verification.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Dict


def canonical_json_bytes(payload: Dict[str, Any]) -> bytes:
    """Deterministic canonicalization: sorted keys, no whitespace."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(b: bytes) -> str:
    """SHA256 hash as hex string."""
    return sha256(b).hexdigest()
