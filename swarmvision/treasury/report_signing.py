"""
SwarmVision Protocol — Payout Report Signing

Signs epoch payout reports for auditability and dispute resolution.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from swarmvision.identity.signing import canonical_json_bytes, sha256_hex
from swarmvision.identity.ethsig import sign_eip191_hash


def sign_payout_report(report_obj: Any, signer_private_key: str) -> Dict[str, Any]:
    """
    Sign a payout report.

    Args:
        report_obj: PayoutReport dataclass
        signer_private_key: Protocol signing key (0x prefixed)

    Returns:
        Dict with report and signature block.
    """
    report_dict = asdict(report_obj)

    # Compute canonical hash
    b = canonical_json_bytes(report_dict)
    h = sha256_hex(b)

    # Sign
    sig = sign_eip191_hash(h, signer_private_key)

    return {
        "report": report_dict,
        "signature": {
            "scheme": "eip191",
            "message_hash": h,
            "signature": sig,
        }
    }
