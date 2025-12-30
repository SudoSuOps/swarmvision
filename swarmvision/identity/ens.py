"""
SwarmVision Protocol — ENS Identity

Identity in SwarmVision is based on ENS (Ethereum Name Service).
No emails, no passwords — just cryptographic signatures.

Naming conventions:
- *.swarmcompute.eth → Compute operators (agents running SwarmAgent)
- *.swarmvision.eth  → Clients (job submitters)

This module provides:
- ENS resolution (mocked for now, pluggable for real ENS)
- Identity verification via signatures
- Role determination (operator vs client)
"""

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class IdentityRole(Enum):
    """Role in the SwarmVision network."""
    OPERATOR = "operator"  # Runs SwarmAgent, executes jobs
    CLIENT = "client"      # Submits jobs, consumes compute
    UNKNOWN = "unknown"


@dataclass
class Identity:
    """A verified identity in SwarmVision."""
    ens_name: str
    address: str  # Ethereum address (0x...)
    role: IdentityRole
    verified: bool = False

    @property
    def is_operator(self) -> bool:
        return self.role == IdentityRole.OPERATOR

    @property
    def is_client(self) -> bool:
        return self.role == IdentityRole.CLIENT


# =============================================================================
# ENS RESOLVER (Mock Implementation)
# =============================================================================

class ENSResolver:
    """
    ENS name resolution.

    This is a mock implementation using a local dictionary.
    In production, this would query the Ethereum mainnet or
    a dedicated ENS deployment.

    The interface is designed for easy replacement.
    """

    def __init__(self):
        # Mock registry: ens_name -> ethereum_address
        self._registry: dict[str, str] = {}

        # Pre-register some test identities
        self._register_mock("operator1.swarmcompute.eth", "0x1111111111111111111111111111111111111111")
        self._register_mock("operator2.swarmcompute.eth", "0x2222222222222222222222222222222222222222")
        self._register_mock("client1.swarmvision.eth", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self._register_mock("client2.swarmvision.eth", "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    def _register_mock(self, ens_name: str, address: str):
        """Register a mock ENS entry."""
        self._registry[ens_name.lower()] = address.lower()

    def resolve(self, ens_name: str) -> Optional[str]:
        """
        Resolve ENS name to Ethereum address.

        Returns None if not found.
        """
        name = ens_name.lower()

        # Check mock registry
        if name in self._registry:
            return self._registry[name]

        # Auto-generate address for unregistered names (for testing)
        # In production, this would return None
        if name.endswith(".eth"):
            # Generate deterministic address from name
            hash_bytes = hashlib.sha256(name.encode()).digest()
            address = "0x" + hash_bytes[:20].hex()
            self._registry[name] = address
            return address

        return None

    def reverse_resolve(self, address: str) -> Optional[str]:
        """
        Reverse resolve: address -> ENS name.

        Returns None if not found.
        """
        addr = address.lower()
        for name, registered_addr in self._registry.items():
            if registered_addr == addr:
                return name
        return None

    def register(self, ens_name: str, address: str) -> bool:
        """
        Register an ENS name (mock).

        In production, this would be an on-chain transaction.
        """
        name = ens_name.lower()

        # Validate name format
        if not self._validate_name(name):
            return False

        # Check if already registered to different address
        existing = self._registry.get(name)
        if existing and existing != address.lower():
            return False

        self._registry[name] = address.lower()
        return True

    def _validate_name(self, name: str) -> bool:
        """Validate ENS name format."""
        # Must end with .eth
        if not name.endswith(".eth"):
            return False

        # Must have at least one subdomain
        parts = name.split(".")
        if len(parts) < 2:
            return False

        # Alphanumeric + hyphens only
        pattern = r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.eth$"
        return bool(re.match(pattern, name))


# =============================================================================
# IDENTITY SERVICE
# =============================================================================

class IdentityService:
    """
    Identity management for SwarmVision.

    Handles:
    - ENS resolution
    - Role determination
    - Signature verification (stubbed)
    """

    def __init__(self, resolver: Optional[ENSResolver] = None):
        self.resolver = resolver or ENSResolver()

    def resolve(self, ens_name: str) -> Optional[Identity]:
        """Resolve ENS name to full identity."""
        address = self.resolver.resolve(ens_name)
        if not address:
            return None

        role = self._determine_role(ens_name)

        return Identity(
            ens_name=ens_name,
            address=address,
            role=role,
            verified=True,
        )

    def _determine_role(self, ens_name: str) -> IdentityRole:
        """Determine role from ENS name.

        Identity namespaces:
        - *.swarmcompute.eth → OPERATOR (runs SwarmAgent, executes jobs)
        - *.swarmvision.eth  → CLIENT (submits jobs, consumes compute)
        - *.eth (generic)    → CLIENT (default for other ENS names)
        """
        name = ens_name.lower()

        if ".swarmcompute.eth" in name or name.endswith("swarmcompute.eth"):
            return IdentityRole.OPERATOR
        elif ".swarmvision.eth" in name or name.endswith("swarmvision.eth"):
            return IdentityRole.CLIENT
        else:
            # Generic .eth names are clients by default
            return IdentityRole.CLIENT

    def verify_signature(
        self,
        message: str,
        signature: str,
        expected_address: str
    ) -> bool:
        """
        Verify a signature against an expected address.

        STUB: In production, this would use ECDSA recovery.
        """
        # Placeholder verification
        # Real implementation would:
        # 1. Hash the message (EIP-191 personal sign)
        # 2. Recover signer address from signature
        # 3. Compare with expected address

        if signature.startswith("sig:"):
            # Accept our placeholder signatures
            return True

        return False

    def register_operator(self, ens_name: str, address: str) -> bool:
        """Register a new operator identity."""
        if not ens_name.endswith(".swarmcompute.eth"):
            # Auto-suffix if needed
            if ens_name.endswith(".eth"):
                return False  # Wrong domain
            ens_name = f"{ens_name}.swarmcompute.eth"

        return self.resolver.register(ens_name, address)

    def register_client(self, ens_name: str, address: str) -> bool:
        """Register a new client identity."""
        if not ens_name.endswith(".swarmvision.eth"):
            if ens_name.endswith(".eth"):
                # Allow generic .eth for clients
                pass
            else:
                ens_name = f"{ens_name}.swarmvision.eth"

        return self.resolver.register(ens_name, address)


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

# Shared identity service instance
_identity_service: Optional[IdentityService] = None


def get_identity_service() -> IdentityService:
    """Get the global identity service instance."""
    global _identity_service
    if _identity_service is None:
        _identity_service = IdentityService()
    return _identity_service


def resolve_identity(ens_name: str) -> Optional[Identity]:
    """Convenience function to resolve an identity."""
    return get_identity_service().resolve(ens_name)


def verify_operator(ens_name: str) -> bool:
    """Check if an ENS name is a valid operator."""
    identity = resolve_identity(ens_name)
    return identity is not None and identity.is_operator


def verify_client(ens_name: str) -> bool:
    """Check if an ENS name is a valid client."""
    identity = resolve_identity(ens_name)
    return identity is not None and identity.is_client
