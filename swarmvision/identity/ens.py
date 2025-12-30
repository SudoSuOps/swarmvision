"""
SwarmVision Protocol — ENS Identity Resolution

Implements ENS.resolution.md spec (v0.2 FINAL).

Two canonical roots:
- swarmvision.eth → Clients
- swarmcompute.eth → Operators

No emails. No passwords. Wallet signatures only.
"""

import re
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
from datetime import datetime, timezone


# =============================================================================
# CONSTANTS
# =============================================================================

# Canonical roots
CLIENT_ROOT = "swarmvision.eth"
OPERATOR_ROOT = "swarmcompute.eth"

# Patterns (normative)
CLIENT_PATTERN = re.compile(r"^[a-z0-9-]+\.swarmvision\.eth$")
OPERATOR_PATTERN = re.compile(r"^[a-z0-9-]+\.swarmcompute\.eth$")

# Reserved labels (MUST NOT be issued)
RESERVED_LABELS = frozenset([
    "www", "api", "docs", "schemas", "admin", "root",
    "treasury", "registry", "status", "health"
])


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class IdentityRole(Enum):
    """Identity role derived from ENS namespace."""
    CLIENT = "client"
    OPERATOR = "operator"
    UNKNOWN = "unknown"


class IdentityStatus(Enum):
    """Identity status from ENS text record."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DRAINING = "draining"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


@dataclass
class ENSRecord:
    """ENS text record."""
    key: str
    value: str


@dataclass
class Identity:
    """
    Resolved ENS identity.

    Contains everything needed for authorization.
    """
    ens_name: str
    role: IdentityRole
    status: IdentityStatus
    address: str  # Owner/controller wallet
    controllers: List[str] = field(default_factory=list)
    records: dict = field(default_factory=dict)
    resolved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_active(self) -> bool:
        """Check if identity is active."""
        return self.status == IdentityStatus.ACTIVE

    @property
    def is_client(self) -> bool:
        """Check if identity is a client."""
        return self.role == IdentityRole.CLIENT

    @property
    def is_operator(self) -> bool:
        """Check if identity is an operator."""
        return self.role == IdentityRole.OPERATOR

    def is_authorized_wallet(self, wallet: str) -> bool:
        """Check if wallet is authorized for this identity."""
        wallet_lower = wallet.lower()
        if self.address.lower() == wallet_lower:
            return True
        return any(c.lower() == wallet_lower for c in self.controllers)


@dataclass
class ResolutionResult:
    """Result of ENS resolution."""
    success: bool
    identity: Optional[Identity] = None
    error: Optional[str] = None


# =============================================================================
# ENS SERVICE
# =============================================================================

class ENSService:
    """
    ENS identity resolution service.

    v0.2: In-memory mock with correct resolution algorithm.
    Production: Replace with real ENS resolution (ethers/web3).
    """

    def __init__(self):
        # Mock registry: ens_name -> Identity
        self._registry: dict[str, Identity] = {}
        # Controller mappings: ens_name -> [wallet addresses]
        self._controllers: dict[str, List[str]] = {}

    def register(
        self,
        ens_name: str,
        address: str,
        controllers: Optional[List[str]] = None,
        records: Optional[dict] = None
    ) -> ResolutionResult:
        """
        Register an ENS identity (mock).

        In production, this reads from ENS on-chain.
        """
        # Validate pattern
        role = self._determine_role(ens_name)
        if role == IdentityRole.UNKNOWN:
            return ResolutionResult(
                success=False,
                error=f"Invalid ENS pattern: {ens_name}"
            )

        # Check reserved labels
        label = ens_name.split(".")[0]
        if label in RESERVED_LABELS:
            return ResolutionResult(
                success=False,
                error=f"Reserved label: {label}"
            )

        # Create identity
        identity = Identity(
            ens_name=ens_name,
            role=role,
            status=IdentityStatus.ACTIVE,
            address=address,
            controllers=controllers or [],
            records=records or {},
        )

        self._registry[ens_name] = identity
        self._controllers[ens_name] = controllers or []

        return ResolutionResult(success=True, identity=identity)

    def resolve(self, ens_name: str) -> Optional[Identity]:
        """
        Resolve ENS name to identity.

        Resolution algorithm (from spec):
        1. Validate pattern
        2. Resolve owner + controllers
        3. Fetch role + status records
        4. Return identity or None
        """
        # Step 1: Validate pattern
        role = self._determine_role(ens_name)
        if role == IdentityRole.UNKNOWN:
            return None

        # Step 2-3: Look up in registry
        identity = self._registry.get(ens_name)
        if identity:
            return identity

        # Auto-register with mock address (for testing)
        address = self._mock_address(ens_name)
        result = self.register(ens_name, address)
        return result.identity

    def resolve_client(self, client_ens: str) -> ResolutionResult:
        """
        Resolve client identity.

        From spec section 6.1:
        1. Validate pattern (*.swarmvision.eth)
        2. Resolve ENS owner + controllers
        3. Fetch role + status records
        4. Confirm role == "client"
        5. Confirm status == "active"
        """
        if not CLIENT_PATTERN.match(client_ens):
            return ResolutionResult(
                success=False,
                error="Invalid client ENS pattern"
            )

        identity = self.resolve(client_ens)
        if not identity:
            return ResolutionResult(
                success=False,
                error="Failed to resolve ENS"
            )

        if identity.role != IdentityRole.CLIENT:
            return ResolutionResult(
                success=False,
                error=f"Expected client role, got {identity.role.value}"
            )

        if not identity.is_active:
            return ResolutionResult(
                success=False,
                error=f"Identity not active: {identity.status.value}"
            )

        return ResolutionResult(success=True, identity=identity)

    def resolve_operator(self, operator_ens: str) -> ResolutionResult:
        """
        Resolve operator identity.

        From spec section 6.2:
        1. Validate pattern (*.swarmcompute.eth)
        2. Resolve ENS owner + controllers
        3. Fetch role + status records
        4. Confirm role == "operator"
        5. Confirm status == "active"
        """
        if not OPERATOR_PATTERN.match(operator_ens):
            return ResolutionResult(
                success=False,
                error="Invalid operator ENS pattern"
            )

        identity = self.resolve(operator_ens)
        if not identity:
            return ResolutionResult(
                success=False,
                error="Failed to resolve ENS"
            )

        if identity.role != IdentityRole.OPERATOR:
            return ResolutionResult(
                success=False,
                error=f"Expected operator role, got {identity.role.value}"
            )

        if not identity.is_active:
            return ResolutionResult(
                success=False,
                error=f"Identity not active: {identity.status.value}"
            )

        return ResolutionResult(success=True, identity=identity)

    def verify_signature_authority(
        self,
        ens_name: str,
        wallet_address: str
    ) -> bool:
        """
        Verify wallet is authorized to sign for ENS identity.

        From spec section 4.2:
        - Owner wallet, OR
        - Approved controller
        """
        identity = self.resolve(ens_name)
        if not identity:
            return False

        if not identity.is_active:
            return False

        return identity.is_authorized_wallet(wallet_address)

    def set_status(self, ens_name: str, status: IdentityStatus) -> bool:
        """
        Set identity status.

        From spec section 9.1:
        - Set suspended/inactive for immediate revocation
        """
        identity = self._registry.get(ens_name)
        if not identity:
            return False

        identity.status = status
        return True

    def add_controller(self, ens_name: str, wallet: str) -> bool:
        """Add authorized controller wallet."""
        identity = self._registry.get(ens_name)
        if not identity:
            return False

        if wallet.lower() not in [c.lower() for c in identity.controllers]:
            identity.controllers.append(wallet)

        return True

    def remove_controller(self, ens_name: str, wallet: str) -> bool:
        """Remove authorized controller wallet."""
        identity = self._registry.get(ens_name)
        if not identity:
            return False

        wallet_lower = wallet.lower()
        identity.controllers = [
            c for c in identity.controllers
            if c.lower() != wallet_lower
        ]

        return True

    def _determine_role(self, ens_name: str) -> IdentityRole:
        """Determine role from ENS namespace."""
        if CLIENT_PATTERN.match(ens_name):
            return IdentityRole.CLIENT
        elif OPERATOR_PATTERN.match(ens_name):
            return IdentityRole.OPERATOR
        return IdentityRole.UNKNOWN

    def _mock_address(self, ens_name: str) -> str:
        """Generate deterministic mock address."""
        hash_bytes = hashlib.sha256(ens_name.encode()).digest()
        return "0x" + hash_bytes[:20].hex()


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_ens_service: Optional[ENSService] = None


def get_identity_service() -> ENSService:
    """Get global ENS service instance."""
    global _ens_service
    if _ens_service is None:
        _ens_service = ENSService()
    return _ens_service


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def resolve_identity(ens_name: str) -> Optional[Identity]:
    """Resolve ENS name to identity."""
    return get_identity_service().resolve(ens_name)


def verify_operator(operator_ens: str) -> ResolutionResult:
    """Verify operator identity."""
    return get_identity_service().resolve_operator(operator_ens)


def verify_client(client_ens: str) -> ResolutionResult:
    """Verify client identity."""
    return get_identity_service().resolve_client(client_ens)


def is_valid_client_ens(ens_name: str) -> bool:
    """Check if ENS name is valid client pattern."""
    return bool(CLIENT_PATTERN.match(ens_name))


def is_valid_operator_ens(ens_name: str) -> bool:
    """Check if ENS name is valid operator pattern."""
    return bool(OPERATOR_PATTERN.match(ens_name))
