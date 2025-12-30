"""
SwarmVision Protocol — Treasury Pool

Pool-based economics for SwarmVision.

Principles:
- Jobs are prepaid with credits
- Operators earn credits for completed work
- Readiness has value (operators stake availability)
- All accounting is transparent

v0.2 Additions:
- Uptime tracking per operator
- Readiness weighting for reward distribution
- Periodic distribution pool for availability rewards

This is an in-memory implementation.
Production would use on-chain accounting or a proper ledger.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from threading import RLock
from typing import Optional
import time


# =============================================================================
# CONSTANTS
# =============================================================================

# Cost per job execution (in credits)
JOB_COST = 10

# Minimum balance to submit jobs
MIN_BALANCE = JOB_COST

# Operator share of job payment (rest goes to protocol)
OPERATOR_SHARE = 0.9  # 90%

# Initial credits for new accounts (for testing)
INITIAL_CREDITS = 100

# Readiness reward pool (v0.2)
READINESS_POOL_SHARE = 0.05  # 5% of protocol fees go to readiness pool
READINESS_DISTRIBUTION_INTERVAL = 3600  # Distribute every hour
MIN_UPTIME_FOR_READINESS = 0.5  # Must be online 50% of epoch to qualify


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class TransactionType(Enum):
    """Types of treasury transactions."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    JOB_PAYMENT = "job_payment"
    JOB_REWARD = "job_reward"
    READINESS_REWARD = "readiness_reward"
    STAKE = "stake"
    UNSTAKE = "unstake"


@dataclass
class Transaction:
    """A treasury transaction."""
    tx_id: str
    timestamp: str
    tx_type: TransactionType
    account: str  # ENS name
    amount: int   # Credits (positive = credit, negative = debit)
    balance_after: int
    reference: str = ""  # job_id, etc.


@dataclass
class Account:
    """An account in the treasury."""
    ens_name: str
    balance: int = INITIAL_CREDITS
    staked: int = 0
    total_earned: int = 0
    total_spent: int = 0
    jobs_submitted: int = 0
    jobs_completed: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class OperatorUptime:
    """
    Tracks operator uptime for readiness rewards.

    v0.2 addition for uptime-weighted distribution.
    """
    ens_name: str
    # Heartbeat tracking
    last_heartbeat: float = 0.0  # Unix timestamp
    heartbeat_count: int = 0
    # Current epoch stats
    epoch_start: float = 0.0
    epoch_online_seconds: float = 0.0
    epoch_heartbeats: int = 0
    # GPU readiness
    gpu_vram_gb: float = 0.0
    gpu_count: int = 0
    is_ready: bool = False  # Has available capacity

    def record_heartbeat(self, vram_gb: float = 0, gpu_count: int = 0):
        """Record a heartbeat from this operator."""
        now = time.time()

        # If this is a new epoch, reset
        if self.epoch_start == 0 or now - self.epoch_start > READINESS_DISTRIBUTION_INTERVAL:
            self.epoch_start = now
            self.epoch_online_seconds = 0
            self.epoch_heartbeats = 0

        # Calculate time since last heartbeat (max 60s to avoid big gaps)
        if self.last_heartbeat > 0:
            time_since = min(now - self.last_heartbeat, 60)
            self.epoch_online_seconds += time_since

        self.last_heartbeat = now
        self.heartbeat_count += 1
        self.epoch_heartbeats += 1
        self.gpu_vram_gb = vram_gb
        self.gpu_count = gpu_count
        self.is_ready = gpu_count > 0 and vram_gb > 0

    @property
    def uptime_ratio(self) -> float:
        """Get uptime ratio for current epoch (0.0 to 1.0)."""
        if self.epoch_start == 0:
            return 0.0
        elapsed = time.time() - self.epoch_start
        if elapsed <= 0:
            return 0.0
        return min(self.epoch_online_seconds / elapsed, 1.0)

    @property
    def is_online(self) -> bool:
        """Check if operator is currently online (heartbeat within 90s)."""
        return time.time() - self.last_heartbeat < 90

    def readiness_weight(self) -> float:
        """
        Calculate readiness weight for reward distribution.

        Weight = uptime_ratio * sqrt(gpu_vram_gb)

        This rewards both reliability and capacity.
        """
        if not self.is_ready or self.uptime_ratio < MIN_UPTIME_FOR_READINESS:
            return 0.0

        # Weight by uptime and GPU capacity
        # sqrt(vram) to avoid excessive concentration to biggest rigs
        import math
        vram_factor = math.sqrt(max(self.gpu_vram_gb, 1))
        return self.uptime_ratio * vram_factor


# =============================================================================
# TREASURY POOL
# =============================================================================

class TreasuryPool:
    """
    In-memory treasury for SwarmVision.

    Thread-safe accounting for credits and payments.

    v0.2: Adds uptime tracking and readiness reward distribution.
    """

    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self._transactions: list[Transaction] = []
        self._lock = RLock()  # Reentrant lock for nested calls
        self._tx_counter = 0

        # Protocol treasury (fees collected)
        self._protocol_balance = 0

        # v0.2: Operator uptime tracking
        self._operator_uptime: dict[str, OperatorUptime] = {}
        self._readiness_pool = 0  # Accumulated readiness rewards
        self._last_distribution = time.time()
        self._distribution_epoch = 0

    def _next_tx_id(self) -> str:
        """Generate next transaction ID."""
        self._tx_counter += 1
        return f"tx_{self._tx_counter:08d}"

    def get_or_create_account(self, ens_name: str) -> Account:
        """Get account, creating if needed."""
        with self._lock:
            if ens_name not in self._accounts:
                self._accounts[ens_name] = Account(ens_name=ens_name)
            return self._accounts[ens_name]

    def get_balance(self, ens_name: str) -> int:
        """Get account balance."""
        account = self.get_or_create_account(ens_name)
        return account.balance

    def deposit(self, ens_name: str, amount: int, reference: str = "") -> Transaction:
        """
        Deposit credits to an account.

        In production, this would be triggered by on-chain payment.
        """
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")

        with self._lock:
            account = self.get_or_create_account(ens_name)
            account.balance += amount

            tx = Transaction(
                tx_id=self._next_tx_id(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                tx_type=TransactionType.DEPOSIT,
                account=ens_name,
                amount=amount,
                balance_after=account.balance,
                reference=reference,
            )
            self._transactions.append(tx)
            return tx

    def can_submit_job(self, ens_name: str) -> bool:
        """Check if account can submit a job."""
        return self.get_balance(ens_name) >= JOB_COST

    def reserve_job_payment(self, client_ens: str, job_id: str) -> Optional[Transaction]:
        """
        Reserve payment for a job.

        Deducts JOB_COST from client balance.
        Returns None if insufficient balance.
        """
        with self._lock:
            account = self.get_or_create_account(client_ens)

            if account.balance < JOB_COST:
                return None

            account.balance -= JOB_COST
            account.total_spent += JOB_COST
            account.jobs_submitted += 1

            tx = Transaction(
                tx_id=self._next_tx_id(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                tx_type=TransactionType.JOB_PAYMENT,
                account=client_ens,
                amount=-JOB_COST,
                balance_after=account.balance,
                reference=job_id,
            )
            self._transactions.append(tx)
            return tx

    def pay_operator(self, operator_ens: str, job_id: str) -> Transaction:
        """
        Pay operator for completed job.

        Operator receives OPERATOR_SHARE of JOB_COST.
        Protocol receives the rest (minus readiness pool contribution).
        """
        operator_payment = int(JOB_COST * OPERATOR_SHARE)
        protocol_fee = JOB_COST - operator_payment

        # v0.2: Allocate portion of protocol fee to readiness pool
        readiness_contribution = int(protocol_fee * READINESS_POOL_SHARE)
        protocol_fee -= readiness_contribution

        with self._lock:
            account = self.get_or_create_account(operator_ens)
            account.balance += operator_payment
            account.total_earned += operator_payment
            account.jobs_completed += 1

            self._protocol_balance += protocol_fee
            self._readiness_pool += readiness_contribution

            tx = Transaction(
                tx_id=self._next_tx_id(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                tx_type=TransactionType.JOB_REWARD,
                account=operator_ens,
                amount=operator_payment,
                balance_after=account.balance,
                reference=job_id,
            )
            self._transactions.append(tx)
            return tx

    def refund_job(self, client_ens: str, job_id: str) -> Transaction:
        """Refund a failed job payment."""
        with self._lock:
            account = self.get_or_create_account(client_ens)
            account.balance += JOB_COST
            account.total_spent -= JOB_COST

            tx = Transaction(
                tx_id=self._next_tx_id(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                tx_type=TransactionType.DEPOSIT,  # Refund is like a deposit
                account=client_ens,
                amount=JOB_COST,
                balance_after=account.balance,
                reference=f"refund:{job_id}",
            )
            self._transactions.append(tx)
            return tx

    def get_account_summary(self, ens_name: str) -> dict:
        """Get account summary."""
        account = self.get_or_create_account(ens_name)
        return {
            "ens_name": account.ens_name,
            "balance": account.balance,
            "staked": account.staked,
            "total_earned": account.total_earned,
            "total_spent": account.total_spent,
            "jobs_submitted": account.jobs_submitted,
            "jobs_completed": account.jobs_completed,
        }

    def get_protocol_stats(self) -> dict:
        """Get protocol-level statistics."""
        with self._lock:
            total_accounts = len(self._accounts)
            total_transactions = len(self._transactions)
            total_credits = sum(a.balance for a in self._accounts.values())
            total_staked = sum(a.staked for a in self._accounts.values())

            # v0.2: Add readiness pool stats
            online_operators = sum(
                1 for u in self._operator_uptime.values() if u.is_online
            )

            return {
                "total_accounts": total_accounts,
                "total_transactions": total_transactions,
                "total_credits_in_circulation": total_credits,
                "total_staked": total_staked,
                "protocol_balance": self._protocol_balance,
                "job_cost": JOB_COST,
                "operator_share": OPERATOR_SHARE,
                # v0.2 fields
                "readiness_pool": self._readiness_pool,
                "online_operators": online_operators,
                "distribution_epoch": self._distribution_epoch,
            }

    # =========================================================================
    # v0.2: UPTIME TRACKING
    # =========================================================================

    def record_operator_heartbeat(
        self,
        operator_ens: str,
        vram_gb: float = 0,
        gpu_count: int = 0
    ):
        """
        Record an operator heartbeat for uptime tracking.

        Called by SwarmVision OS when receiving heartbeats.
        """
        with self._lock:
            if operator_ens not in self._operator_uptime:
                self._operator_uptime[operator_ens] = OperatorUptime(
                    ens_name=operator_ens
                )
            self._operator_uptime[operator_ens].record_heartbeat(vram_gb, gpu_count)

            # Check if distribution is due
            self._maybe_distribute_readiness()

    def get_operator_uptime(self, operator_ens: str) -> Optional[OperatorUptime]:
        """Get uptime stats for an operator."""
        return self._operator_uptime.get(operator_ens)

    def get_online_operators(self) -> list[OperatorUptime]:
        """Get list of currently online operators."""
        return [u for u in self._operator_uptime.values() if u.is_online]

    # =========================================================================
    # v0.2: READINESS DISTRIBUTION
    # =========================================================================

    def _maybe_distribute_readiness(self):
        """
        Check if readiness distribution is due and execute if so.

        Called during heartbeat processing (already under lock).
        """
        now = time.time()
        if now - self._last_distribution < READINESS_DISTRIBUTION_INTERVAL:
            return

        if self._readiness_pool <= 0:
            self._last_distribution = now
            return

        self._distribute_readiness_rewards()

    def _distribute_readiness_rewards(self):
        """
        Distribute readiness pool to qualifying operators.

        Weighted by uptime ratio * sqrt(VRAM).
        Must be called while holding lock.
        """
        self._distribution_epoch += 1
        self._last_distribution = time.time()

        # Calculate total weight
        weights: dict[str, float] = {}
        total_weight = 0.0

        for ens, uptime in self._operator_uptime.items():
            weight = uptime.readiness_weight()
            if weight > 0:
                weights[ens] = weight
                total_weight += weight

        if total_weight <= 0 or not weights:
            # No qualifying operators, carry over to next epoch
            return

        # Distribute proportionally
        pool_to_distribute = self._readiness_pool
        self._readiness_pool = 0

        for ens, weight in weights.items():
            share = int(pool_to_distribute * (weight / total_weight))
            if share <= 0:
                continue

            # Get or create account (without lock - we're already holding it)
            if ens not in self._accounts:
                self._accounts[ens] = Account(ens_name=ens)
            account = self._accounts[ens]

            account.balance += share
            account.total_earned += share

            tx = Transaction(
                tx_id=self._next_tx_id(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                tx_type=TransactionType.READINESS_REWARD,
                account=ens,
                amount=share,
                balance_after=account.balance,
                reference=f"epoch:{self._distribution_epoch}",
            )
            self._transactions.append(tx)

        # Reset epoch stats for all operators
        for uptime in self._operator_uptime.values():
            uptime.epoch_start = time.time()
            uptime.epoch_online_seconds = 0
            uptime.epoch_heartbeats = 0

    def force_readiness_distribution(self) -> dict:
        """
        Force immediate readiness distribution (for testing/admin).

        Returns distribution summary.
        """
        with self._lock:
            pool_before = self._readiness_pool
            operators_before = len([u for u in self._operator_uptime.values()
                                   if u.readiness_weight() > 0])

            self._distribute_readiness_rewards()

            return {
                "pool_distributed": pool_before,
                "qualifying_operators": operators_before,
                "epoch": self._distribution_epoch,
            }

    def get_readiness_status(self) -> dict:
        """Get current readiness pool status."""
        with self._lock:
            operators = []
            for ens, uptime in self._operator_uptime.items():
                operators.append({
                    "ens_name": ens,
                    "is_online": uptime.is_online,
                    "uptime_ratio": round(uptime.uptime_ratio, 3),
                    "gpu_vram_gb": uptime.gpu_vram_gb,
                    "readiness_weight": round(uptime.readiness_weight(), 3),
                    "heartbeats_this_epoch": uptime.epoch_heartbeats,
                })

            time_to_next = max(
                0,
                READINESS_DISTRIBUTION_INTERVAL - (time.time() - self._last_distribution)
            )

            return {
                "pool_balance": self._readiness_pool,
                "current_epoch": self._distribution_epoch,
                "seconds_to_distribution": int(time_to_next),
                "operators": sorted(
                    operators,
                    key=lambda x: x["readiness_weight"],
                    reverse=True
                ),
            }

    def get_transactions(
        self,
        ens_name: Optional[str] = None,
        limit: int = 100
    ) -> list[Transaction]:
        """Get transactions, optionally filtered by account."""
        with self._lock:
            txs = self._transactions
            if ens_name:
                txs = [t for t in txs if t.account == ens_name]
            return list(reversed(txs[-limit:]))


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_treasury: Optional[TreasuryPool] = None


def get_treasury() -> TreasuryPool:
    """Get the global treasury instance."""
    global _treasury
    if _treasury is None:
        _treasury = TreasuryPool()
    return _treasury
