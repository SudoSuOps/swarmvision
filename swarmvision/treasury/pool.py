"""
SwarmVision Protocol — Treasury Pool

Pool-based economics for SwarmVision.

Principles:
- Jobs are prepaid with credits
- Operators earn credits for completed work
- Readiness has value (operators stake availability)
- All accounting is transparent

This is an in-memory implementation.
Production would use on-chain accounting or a proper ledger.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Optional


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


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class TransactionType(Enum):
    """Types of treasury transactions."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    JOB_PAYMENT = "job_payment"
    JOB_REWARD = "job_reward"
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


# =============================================================================
# TREASURY POOL
# =============================================================================

class TreasuryPool:
    """
    In-memory treasury for SwarmVision.

    Thread-safe accounting for credits and payments.
    """

    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self._transactions: list[Transaction] = []
        self._lock = Lock()
        self._tx_counter = 0

        # Protocol treasury (fees collected)
        self._protocol_balance = 0

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
        Protocol receives the rest.
        """
        operator_payment = int(JOB_COST * OPERATOR_SHARE)
        protocol_fee = JOB_COST - operator_payment

        with self._lock:
            account = self.get_or_create_account(operator_ens)
            account.balance += operator_payment
            account.total_earned += operator_payment
            account.jobs_completed += 1

            self._protocol_balance += protocol_fee

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

            return {
                "total_accounts": total_accounts,
                "total_transactions": total_transactions,
                "total_credits_in_circulation": total_credits,
                "total_staked": total_staked,
                "protocol_balance": self._protocol_balance,
                "job_cost": JOB_COST,
                "operator_share": OPERATOR_SHARE,
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
