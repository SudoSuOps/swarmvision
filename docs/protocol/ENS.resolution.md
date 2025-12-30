# ENS Identity Resolution Spec

> **Protocol Version:** v0.2
> **Status:** FINAL — No breaking changes without major version bump.

## 1. Purpose

SwarmVision uses ENS names as primary identifiers. No emails. No passwords.

This spec defines:
- Namespace rules
- Role classification (client vs operator)
- Authentication via wallet signatures
- Resolution algorithm
- Key rotation model

## 2. Canonical Roots

| Root | Purpose |
|------|---------|
| `swarmvision.eth` | Governance / OS / client namespace |
| `swarmcompute.eth` | Execution namespace for operators |

These are **distinct trust domains**.

## 3. Roles and Namespace Rules

### 3.1 Client Identity

**Pattern:** `^[a-z0-9-]+\.swarmvision\.eth$`

**Examples:**
- `xyzmed.swarmvision.eth`
- `lab-17.swarmvision.eth`

**Represents:**
- Billing namespace
- Audit namespace
- Job submission authority

### 3.2 Operator Identity

**Pattern:** `^[a-z0-9-]+\.swarmcompute\.eth$`

**Examples:**
- `rig42.swarmcompute.eth`
- `nj-10g-01.swarmcompute.eth`

**Represents:**
- Execution authority (proof signing)
- Reputation identity
- Payout identity

### 3.3 Reserved Labels

The following MUST NOT be issued:

```
www, api, docs, schemas, admin, root, treasury, registry, status, health
```

## 4. Authentication Model

### 4.1 Wallet-Based Authentication

All authenticated actions MUST be signed by an authorized wallet.

**Client actions:**
- Submit job
- Query job status
- Retrieve results/proofs

**Operator actions:**
- Heartbeats
- Capability reports
- PoE submission

### 4.2 Authorization Methods

#### A) ENS Controller Ownership (Direct)

Request authorized if signing wallet is:
- ENS name owner, OR
- Approved controller

Verification:
1. Resolve ENS name → owner address
2. Verify signature against owner
3. Accept if valid

#### B) Authorized Operator (Recommended)

ENS names MAY delegate to wallets via:
- ENS controllers
- Text records
- Contract resolvers (future)

Enables:
- Hot wallets
- Machine keys
- Key rotation
- Revocation without renaming

## 5. ENS Resolution Requirements

### 5.1 Mandatory Records

**Client ENS (`*.swarmvision.eth`):**

| Record | Purpose |
|--------|---------|
| `owner` | Root authority |
| `resolver` | ENS resolver |
| `text:swarmvision.role` | MUST equal `client` |
| `text:swarmvision.status` | `active` / `suspended` |

**Operator ENS (`*.swarmcompute.eth`):**

| Record | Purpose |
|--------|---------|
| `owner` | Root authority |
| `resolver` | ENS resolver |
| `text:swarmvision.role` | MUST equal `operator` |
| `text:swarmvision.status` | `active` / `draining` / `inactive` |

Requests from non-`active` identities MUST be rejected.

### 5.2 Optional Records

| Record | Description |
|--------|-------------|
| `text:swarmvision.endpoint` | Preferred mesh/API endpoint |
| `text:swarmvision.region` | Geographic hint |
| `text:swarmvision.hardware` | Capability hint |
| `text:swarmvision.version` | Agent/OS compatibility |

Advisory only. MUST NOT be trusted for security.

## 6. Resolution Algorithm

### 6.1 Resolve Client Identity

```
Input: client_ens

1. Validate pattern (*.swarmvision.eth)
2. Resolve ENS owner + controllers
3. Fetch role + status records
4. Confirm role == "client"
5. Confirm status == "active"
6. Authorize signed request
```

### 6.2 Resolve Operator Identity

```
Input: operator_ens

1. Validate pattern (*.swarmcompute.eth)
2. Resolve ENS owner + controllers
3. Fetch role + status records
4. Confirm role == "operator"
5. Confirm status == "active"
6. Accept PoE signatures from authorized wallets
```

## 7. Identity → Protocol Mapping

### 7.1 Client ENS Grants

- Job submission
- Job query
- Proof retrieval
- Billing balance consumption

**Clients NEVER:**
- Route jobs
- Verify PoE
- Participate in payouts

### 7.2 Operator ENS Grants

- SwarmAgent execution
- Proof of Execution signing
- Capability reporting
- Treasury payout eligibility

**Operators NEVER:**
- Submit jobs as clients
- Modify pricing
- Override routing rules

## 8. Identity & Proof of Execution

Every PoE MUST include:
```json
{
  "operator": {
    "operator_ens": "rig42.swarmcompute.eth",
    "wallet": {
      "address": "0x..."
    }
  }
}
```

SwarmVision MUST verify:
1. Wallet is authorized for `operator_ens`
2. Signature matches PoE message hash
3. ENS status was `active` at execution time

**Any check fails → PoE invalid.**

## 9. Revocation & Rotation

### 9.1 Immediate Revocation

Set `text:swarmvision.status = suspended|inactive`

Takes effect immediately.

### 9.2 Key Rotation

1. Add new controller wallet
2. Remove old controller wallet

No protocol changes required.

## 10. No Identity Storage Rule

SwarmVision MUST NOT:
- Store ENS private keys
- Cache wallet secrets
- Maintain account databases

Identity resolved at request time.

## 11. Security Model

| Threat | Mitigation |
|--------|------------|
| Account takeover | No passwords |
| Insider abuse | Signed actions |
| Impersonation | ENS ownership |
| Replay | Signed PoE hashes |
| Central failure | Decentralized identity |

## 12. Future Extensions

- ENS offchain resolvers (CCIP-Read)
- DID compatibility
- Multi-sig operator identities
- Hardware-backed signing (HSM/TPM)

MUST NOT break v0.2 resolution rules.

---

*This spec is FINAL for SwarmVision Protocol v0.2.*
