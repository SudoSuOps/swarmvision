"""
SwarmVision Protocol — Ethereum Signature Verification

EIP-191 personal_sign verification using eth_account.
"""

from __future__ import annotations

from typing import Dict, Any
from eth_account import Account
from eth_account.messages import encode_defunct


def recover_eip191_address(message_hash_hex: str, signature_hex: str) -> str:
    """
    Recover signer address from EIP-191 personal_sign signature.

    Args:
        message_hash_hex: 32-byte hash as hex (no 0x prefix)
        signature_hex: Signature from wallet (0x prefixed)

    Returns:
        Recovered address (lowercase).
    """
    msg = encode_defunct(hexstr="0x" + message_hash_hex)
    addr = Account.recover_message(msg, signature=signature_hex)
    return addr.lower()


def sign_eip191_hash(message_hash_hex: str, private_key_hex: str) -> str:
    """
    Sign a message hash with EIP-191 personal_sign.

    Args:
        message_hash_hex: 32-byte hash as hex (no 0x prefix)
        private_key_hex: Private key (0x prefixed)

    Returns:
        Hex signature.
    """
    msg = encode_defunct(hexstr="0x" + message_hash_hex)
    signed = Account.sign_message(msg, private_key=private_key_hex)
    return signed.signature.hex()
