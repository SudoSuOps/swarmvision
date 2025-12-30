# BEE-23: Proof of Compute Protocol Specification

**Status:** Draft
**Version:** 0.1
**Date:** 2025-12-30
**Authors:** QuantumSwarm Protocol Team

---

## Abstract

BEE-23 is a Proof of Compute (PoC) algorithm that defines valid compute, verification rules, reward distribution, and fraud rejection for the Swarm network. BEE-23 is to Swarm what SHA-256 is to Bitcoin: the consensus mechanism that makes the network trustless.

This document specifies BEE-23 in its entirety.

---

## 1. Motivation

Cloud compute is broken. It requires trust in:
- The provider (data retention, pricing, availability)
- The infrastructure (multi-tenant, opaque, unverifiable)
- The economics (usage-based, vendor lock-in, price manipulation)

BEE-23 eliminates trust by making compute:
- **Verifiable**: Every execution produces cryptographic proof
- **Deterministic**: Rules are enforced by protocol, not policy
- **Sovereign**: Operators own their hardware and identity

There is no governance. There is no discretion. There is only the algorithm.

---

## 2. Definitions

### 2.1 Core Terms

| Term | Definition |
|------|------------|
| **Bee** | A sovereign compute node running Swarm-OS |
| **Swarm-OS** | The execution and verification layer that enforces BEE-23 |
| **EPOCH** | A discrete accounting window (analogous to a Bitcoin block) |
| **Proof of Compute (PoC)** | Cryptographic attestation that work was performed |
| **Execution Receipt** | Signed record of a completed compute job |
| **Treasury** | Protocol-controlled pool that holds prepaid job revenue |

### 2.2 Notation

```
H(x)        = SHA-256 hash of x
SIG(k, m)   = ECDSA signature of message m with private key k
VERIFY(a, m, s) = Signature verification (address a, message m, signature s)
||          = Concatenation
TS          = Unix timestamp (seconds)
```

---

## 3. BEE-23 Algorithm

### 3.1 Proof of Compute Structure

A valid Proof of Compute (PoC) contains:

```
PoC = {
    protocol:    { name: "swarm", version: "bee-23" },
    poc_id:      H(job_id || operator_ens || started_at),

    job: {
        job_id:      string,          // Unique job identifier
        client_ens:  string,          // Client identity (ENS)
        task_hash:   H(task_payload), // Hash of job specification
        submitted_at: TS,             // When job was submitted
        prepaid:     uint64,          // Credits prepaid for job
    },

    operator: {
        operator_ens: string,         // Operator identity (ENS)
        wallet: {
            chain:   "ethereum",
            address: address,         // Operator's signing address
        },
        hardware: {
            gpu_id:    string,        // GPU identifier
            vram_bytes: uint64,       // VRAM capacity
        },
    },

    execution: {
        started_at:  TS,              // Execution start timestamp
        ended_at:    TS,              // Execution end timestamp
        duration_ms: uint64,          // Wall-clock duration
        compute_units: uint64,        // Normalized compute measurement
    },

    artifact: {
        output_hash: H(output),       // Hash of execution output
        output_size: uint64,          // Output size in bytes
    },

    signature: {
        scheme:       "eip191",
        message_hash: H(PoC_without_signature),
        signature:    SIG(operator_key, message_hash),
    }
}
```

### 3.2 PoC Validity Rules

A PoC is **VALID** if and only if ALL conditions hold:

1. **Signature Valid**
   ```
   VERIFY(operator.wallet.address, signature.message_hash, signature.signature) == true
   ```

2. **Hash Chain Valid**
   ```
   signature.message_hash == H(canonical_json(PoC_without_signature))
   ```

3. **Timing Valid**
   ```
   execution.ended_at > execution.started_at
   execution.duration_ms == (execution.ended_at - execution.started_at) * 1000
   execution.ended_at <= current_time + MAX_CLOCK_DRIFT
   ```

4. **Job Exists**
   ```
   job.job_id exists in Swarm-OS job registry
   job.prepaid > 0
   ```

5. **Operator Registered**
   ```
   operator.operator_ens is registered in Swarm-OS
   operator.wallet.address matches registered wallet
   ```

6. **No Duplicate**
   ```
   poc_id not in processed_pocs
   ```

A PoC that fails ANY condition is **REJECTED**. There are no exceptions.

### 3.3 Compute Unit Calculation

Compute units normalize heterogeneous hardware:

```
compute_units = base_units(task_type) * duration_factor * hardware_factor

where:
    base_units(task_type) = predefined per task type
    duration_factor = execution.duration_ms / expected_duration_ms
    hardware_factor = min(1.0, actual_vram / required_vram)
```

Compute units are the unit of account for reward distribution.

---

## 4. EPOCH Mechanics

### 4.1 EPOCH Definition

An EPOCH is an immutable accounting window with:

```
EPOCH = {
    epoch_id:     uint64,            // Sequential epoch number
    start_ts:     TS,                // Epoch start timestamp
    end_ts:       TS,                // Epoch end timestamp
    duration:     EPOCH_DURATION,    // Fixed: 86400 seconds (24 hours)

    // Accumulated during epoch
    jobs_submitted:    uint64,
    jobs_completed:    uint64,
    total_compute:     uint64,       // Sum of compute_units
    gross_revenue:     uint64,       // Sum of prepaid credits

    // Per-operator accumulation
    operators: Map<ens_name, {
        compute_units:  uint64,
        jobs_completed: uint64,
        heartbeats:     uint64,
        last_seen:      TS,
    }>,

    // State
    status: "open" | "closing" | "closed",
}
```

### 4.2 EPOCH Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                         EPOCH LIFECYCLE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌────────┐ │
│  │  EPOCH   │────▶│  EPOCH   │────▶│  EPOCH   │────▶│ EPOCH  │ │
│  │   OPEN   │     │ CLOSING  │     │  SETTLE  │     │ CLOSED │ │
│  └──────────┘     └──────────┘     └──────────┘     └────────┘ │
│       │                │                │                │      │
│       ▼                ▼                ▼                ▼      │
│   Accept jobs     No new jobs      Distribute       Immutable  │
│   Accept PoCs     Final PoCs       rewards          history    │
│   Heartbeats      Calculate        Update                      │
│                   totals           balances                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Phase 1: OPEN** (duration: EPOCH_DURATION - CLOSING_WINDOW)
- Jobs are submitted and assigned
- PoCs are accepted and validated
- Operator heartbeats are recorded
- Compute units accumulate

**Phase 2: CLOSING** (duration: CLOSING_WINDOW, default 300 seconds)
- No new jobs accepted
- Final PoCs accepted (for jobs started during OPEN)
- Totals calculated
- Reward shares computed

**Phase 3: SETTLE** (instantaneous)
- Treasury distributes rewards
- Operator balances updated
- Protocol fee extracted

**Phase 4: CLOSED** (permanent)
- Epoch data immutable
- No retroactive changes
- Historical record preserved

### 4.3 EPOCH Close Algorithm

```python
def close_epoch(epoch):
    assert epoch.status == "closing"
    assert current_time >= epoch.end_ts

    # Calculate total compute
    total_compute = sum(op.compute_units for op in epoch.operators.values())

    if total_compute == 0:
        # No compute performed - no distribution
        epoch.status = "closed"
        return

    # Calculate distributable revenue
    gross = epoch.gross_revenue
    protocol_fee = gross * PROTOCOL_FEE_RATE  # 10%
    distributable = gross - protocol_fee

    # Distribute proportionally to compute
    for ens, op in epoch.operators.items():
        if op.compute_units > 0:
            share = op.compute_units / total_compute
            reward = distributable * share
            credit_account(ens, reward)

    # Protocol fee to treasury
    credit_account(PROTOCOL_TREASURY, protocol_fee)

    epoch.status = "closed"

    # Emit settlement event
    emit EpochSettled(epoch.epoch_id, total_compute, distributable)
```

---

## 5. Bee Node Specification

### 5.1 Bee Identity

A Bee is identified by:

```
Bee = {
    ens_name:    "*.swarmcompute.eth",  // ENS subdomain
    wallet:      ethereum_address,       // Signing wallet
    public_key:  secp256k1_pubkey,       // Derived from wallet
}
```

**Identity Rules:**
- No email. No KYC. No registration forms.
- Identity is cryptographic: you are your keys
- ENS provides human-readable naming
- Wallet provides signing capability

### 5.2 Bee States

```
         ┌─────────────────┐
         │                 │
         ▼                 │
    ┌─────────┐      ┌─────────┐
    │ OFFLINE │◀────▶│ ONLINE  │
    └─────────┘      └─────────┘
         │                 │
         │                 ▼
         │           ┌─────────┐
         └──────────▶│SUSPENDED│
                     └─────────┘
```

**OFFLINE**
- No heartbeats received for > HEARTBEAT_TIMEOUT (90 seconds)
- Not eligible for job assignment
- Earns zero rewards

**ONLINE**
- Heartbeat received within HEARTBEAT_TIMEOUT
- Eligible for job assignment
- Accumulates compute units from completed jobs

**SUSPENDED**
- Repeated PoC validation failures
- Temporary exclusion from job assignment
- Must re-register to resume

### 5.3 Bee Lifecycle

```python
class Bee:
    def register(self, ens_name, wallet):
        """Register a new Bee with Swarm-OS"""
        assert ens_name.endswith(".swarmcompute.eth")
        assert wallet is valid ethereum address
        assert ens_name not in registered_bees

        self.ens_name = ens_name
        self.wallet = wallet
        self.status = "offline"
        self.registered_at = now()

    def heartbeat(self, hardware_report):
        """Send periodic heartbeat to maintain ONLINE status"""
        self.last_heartbeat = now()
        self.hardware = hardware_report
        self.status = "online"

        # Record in current epoch
        current_epoch.operators[self.ens_name].heartbeats += 1
        current_epoch.operators[self.ens_name].last_seen = now()

    def execute(self, job):
        """Execute a job and produce PoC"""
        assert self.status == "online"

        started_at = now()
        output = run_workload(job.payload)
        ended_at = now()

        poc = create_poc(job, self, started_at, ended_at, output)
        poc.signature = sign(poc, self.wallet)

        submit_poc(poc)
        return poc
```

### 5.4 Eligibility Rules

A Bee is **ELIGIBLE** for rewards in an EPOCH if:

1. **Registered**: `ens_name` in Swarm-OS registry
2. **Compute Performed**: `compute_units > 0` for that epoch
3. **Valid PoCs**: All submitted PoCs passed validation

**Critical Rule:**
> Bees that compute earn. Bees that do not compute do not earn.

There is no staking reward.
There is no delegation.
There is no reputation bonus.
There is no "availability" payment without work.

Offline Bees earn zero, exactly like offline Bitcoin miners.

---

## 6. Verification Flow

### 6.1 PoC Submission and Verification

```
┌─────────┐         ┌───────────┐         ┌──────────┐
│   Bee   │         │ Swarm-OS  │         │ Treasury │
└────┬────┘         └─────┬─────┘         └────┬─────┘
     │                    │                    │
     │  1. Execute Job    │                    │
     │ ─────────────────▶ │                    │
     │                    │                    │
     │  2. Submit PoC     │                    │
     │ ─────────────────▶ │                    │
     │                    │                    │
     │                    │  3. Validate       │
     │                    │ ────────────────── │
     │                    │                    │
     │                    │  4. If Valid:      │
     │                    │     Record         │
     │                    │ ─────────────────▶ │
     │                    │                    │
     │  5. ACK/NACK       │                    │
     │ ◀───────────────── │                    │
     │                    │                    │
```

### 6.2 Validation Algorithm

```python
def validate_poc(poc):
    """
    Validate a Proof of Compute.
    Returns (valid: bool, reason: str)
    """

    # 1. Schema validation
    if not valid_schema(poc):
        return False, "INVALID_SCHEMA"

    # 2. Signature verification
    message_hash = sha256(canonical_json(poc_without_signature(poc)))
    if message_hash != poc.signature.message_hash:
        return False, "HASH_MISMATCH"

    recovered = ecrecover(poc.signature.message_hash, poc.signature.signature)
    if recovered.lower() != poc.operator.wallet.address.lower():
        return False, "SIGNATURE_INVALID"

    # 3. Job existence
    job = get_job(poc.job.job_id)
    if job is None:
        return False, "JOB_NOT_FOUND"

    # 4. Operator registration
    operator = get_operator(poc.operator.operator_ens)
    if operator is None:
        return False, "OPERATOR_NOT_REGISTERED"

    if operator.wallet != poc.operator.wallet.address:
        return False, "WALLET_MISMATCH"

    # 5. Timing validation
    if poc.execution.ended_at <= poc.execution.started_at:
        return False, "INVALID_TIMING"

    expected_duration = poc.execution.ended_at - poc.execution.started_at
    if abs(poc.execution.duration_ms - expected_duration * 1000) > 1000:
        return False, "DURATION_MISMATCH"

    # 6. Duplicate check
    if poc.poc_id in processed_pocs:
        return False, "DUPLICATE_POC"

    # 7. Epoch check
    if poc.execution.ended_at < current_epoch.start_ts:
        return False, "EPOCH_EXPIRED"

    # All checks passed
    return True, "VALID"
```

---

## 7. Economic Model

### 7.1 Job Pricing

All jobs are **prepaid**. No credit, no promises, no invoices.

```
job_cost = base_cost(task_type) * estimated_compute_units

where:
    base_cost = protocol-defined per task type
    estimated_compute_units = task complexity estimate
```

### 7.2 Revenue Flow

```
┌────────────────────────────────────────────────────────────────┐
│                        REVENUE FLOW                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Client                Treasury              Operators         │
│    │                      │                      │             │
│    │  Prepay Job          │                      │             │
│    │ ───────────────────▶ │                      │             │
│    │                      │                      │             │
│    │                      │  [EPOCH CLOSE]       │             │
│    │                      │                      │             │
│    │                      │  90% to Operators    │             │
│    │                      │ ───────────────────▶ │             │
│    │                      │  (proportional to    │             │
│    │                      │   compute_units)     │             │
│    │                      │                      │             │
│    │                      │  10% Protocol Fee    │             │
│    │                      │ ──────────┐          │             │
│    │                      │           │          │             │
│    │                      │ ◀─────────┘          │             │
│    │                      │  (retained)          │             │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 7.3 Distribution Formula

At EPOCH close:

```
For each operator O with compute_units C_O:

    total_compute = Σ C_i for all operators i

    if C_O > 0:
        share = C_O / total_compute
        reward = (gross_revenue * 0.90) * share
        credit(O, reward)
    else:
        reward = 0
```

**No compute = No reward. No exceptions.**

---

## 8. Threat Model

### 8.1 Attack Vectors and Mitigations

| Attack | Description | Mitigation |
|--------|-------------|------------|
| **Fake Compute** | Submit PoC without executing | Output hash verification, spot checks |
| **Replay Attack** | Resubmit old PoC | poc_id uniqueness, epoch bounds |
| **Idle Freeloader** | Claim availability without work | No availability reward, compute-only |
| **GPU Inflation** | Claim more hardware than owned | Hardware attestation, compute benchmarks |
| **Timestamp Manipulation** | Fake execution duration | Clock drift limits, duration bounds |
| **Sybil Attack** | Multiple identities, one machine | Per-job assignment, hardware fingerprint |

### 8.2 Security Assumptions

BEE-23 assumes:

1. **ECDSA is secure**: Signatures cannot be forged
2. **SHA-256 is collision-resistant**: Hashes uniquely identify content
3. **Operators are rational**: They maximize profit, not chaos
4. **Network is asynchronous**: Messages may be delayed, not lost

BEE-23 does NOT assume:

1. Operators are honest
2. Clients are honest
3. Network is reliable
4. Clocks are synchronized
5. Hardware reports are accurate

---

## 9. Constants

```
EPOCH_DURATION        = 86400      # 24 hours in seconds
CLOSING_WINDOW        = 300        # 5 minutes
HEARTBEAT_INTERVAL    = 30         # seconds
HEARTBEAT_TIMEOUT     = 90         # seconds (3 missed = offline)
MAX_CLOCK_DRIFT       = 60         # seconds
PROTOCOL_FEE_RATE     = 0.10       # 10%
MIN_COMPUTE_UNITS     = 1          # Minimum for reward eligibility
```

---

## 10. Reference Implementation

See: `swarmvision/os/core.py`

The reference implementation provides:
- EPOCH management
- PoC validation
- Reward distribution
- Bee registration and heartbeat

---

## 11. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-12-30 | Initial specification |

---

## 12. References

1. Bitcoin Whitepaper - Satoshi Nakamoto (2008)
2. EIP-191: Signed Data Standard
3. EIP-712: Typed Structured Data Hashing and Signing
4. ENS: Ethereum Name Service Specification

---

*BEE-23 is protocol, not policy. Code is law.*

🐝
