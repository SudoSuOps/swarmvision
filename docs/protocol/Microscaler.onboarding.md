# Microscaler Onboarding Specification

> **Protocol Version:** v0.2
> **Status:** FINAL

## 1. Purpose

This document defines how a Microscaler joins the SwarmVision network as a trusted compute provider.

A Microscaler is a human-operated, sovereign compute node that contributes execution capacity to the Swarm in exchange for pooled rewards.

This spec covers:
- Eligibility requirements
- Identity creation
- Software installation
- Verification & activation
- Ongoing obligations
- Exit & revocation

## 2. Definition: Microscaler

A Microscaler is:
- An independent operator
- Running owned hardware
- Providing always-on compute
- Executing jobs ephemerally
- Identified by ENS
- Paid via the Swarm Treasury pool

**Microscalers are partners, not renters, contractors, or regions.**

## 3. Eligibility Requirements

### 3.1 Hardware

A Microscaler MUST have:
- ≥ 1 modern GPU (NVIDIA or AMD supported)
- Recommended: 8–10 high-end GPUs for optimal routing
- Sufficient VRAM for declared tasks
- Adequate cooling and physical security

### 3.2 Network

- Stable broadband or fiber connection
- Low packet loss
- Ability to run encrypted mesh networking (Tailscale/Headscale)
- No requirement for public inbound ports

### 3.3 Power

- Grid power
- Recommended:
  - Battery backup (UPS or equivalent)
  - Secondary connectivity (e.g., Starlink)

### 3.4 Operator

- Human operator available for maintenance
- Commitment to 24/7 readiness
- Willingness to follow protocol rules

## 4. Identity Creation

### 4.1 ENS Registration

Each Microscaler MUST control an ENS name under:

```
*.swarmcompute.eth
```

Examples:
- `rig42.swarmcompute.eth`
- `nyc-01.swarmcompute.eth`

This ENS name is the **sole identity** of the Microscaler.

### 4.2 ENS Records

Required records:

| Record | Value |
|--------|-------|
| `text:swarmvision.role` | `operator` |
| `text:swarmvision.status` | `active` |
| Controller | Wallet used by SwarmAgent |

Optional (advisory):
- `text:swarmvision.region`
- `text:swarmvision.hardware`

## 5. Software Installation

### 5.1 SwarmAgent

Microscalers MUST run SwarmAgent, the Swarm execution daemon.

Installation MUST:
- Be CLI-first
- Support unattended startup
- Run as a background service
- Auto-restart on failure

```bash
curl -fsSL https://swarmvision.eth/install | bash
```

### 5.2 Configuration

Required environment variables:

```bash
SWARMCOMPUTE_ENS=rig42.swarmcompute.eth
SWARMVISION_URL=http://swarmvision.mesh:8000
SWARMAGENT_PRIVATE_KEY=****
```

The private key MUST:
- Control the ENS identity
- Be stored securely
- Never be transmitted

## 6. Network Connectivity

### 6.1 Mesh Requirement

Microscalers MUST connect via an encrypted mesh network.

Requirements:
- End-to-end encryption
- Private addressing
- Automatic reconnection

**Public exposure of compute endpoints is strongly discouraged.**

## 7. Verification & Activation

### 7.1 Initial Handshake

Upon startup, SwarmAgent MUST:
1. Resolve its ENS identity
2. Sign a registration message
3. Submit capability report
4. Begin heartbeat loop

### 7.2 Capability Report

Reported capabilities:
- CPU model + cores
- RAM
- GPU model(s)
- VRAM
- Driver versions

Capabilities are used for **routing, not identity**.

### 7.3 Activation

A Microscaler becomes active when:
- ENS identity resolves correctly
- Heartbeats are received
- Capability report is valid

**No manual approval is required in v0.2.**

## 8. Operational Obligations

Microscalers MUST:
- Maintain accurate capability reporting
- Respond to jobs promptly
- Execute jobs ephemerally
- Generate valid Proofs of Execution
- Maintain uptime consistent with declared readiness

Microscalers MUST NOT:
- Store client data
- Reuse job data
- Inspect or log sensitive payloads
- Modify artifacts or execution logic

## 9. Proof of Execution Requirement

For every job executed, the Microscaler MUST submit a valid:

```
ProofOfExecution v0.2
```

PoE MUST:
- Be signed by the operator wallet
- Reference the correct ENS identity
- Match execution timestamps
- Include artifact and result hashes

**Invalid PoE → no payout.**

## 10. Economics & Pool Participation

### 10.1 Treasury Pool

Microscalers are paid from the Swarm Treasury pool.

Rewards are weighted by:
- Uptime
- Availability
- Jobs completed
- Reputation score

**Idle but available compute is rewarded.**

### 10.2 No Per-Job Negotiation

Microscalers do not bid on jobs. They participate in the pool.

This ensures:
- Stability
- Predictable income
- Fast routing
- High SLA confidence

## 11. Reputation & Enforcement

SwarmVision tracks:
- Heartbeat consistency
- Job acceptance
- PoE validity
- Failure rates

Penalties may include:
- Reduced routing
- Reduced payout weight
- Status change (`draining`, `inactive`)

## 12. Exit & Revocation

### 12.1 Voluntary Exit

A Microscaler may exit by:
1. Setting `text:swarmvision.status = inactive`
2. Shutting down SwarmAgent

**No lock-in exists.**

### 12.2 Forced Revocation

SwarmVision may mark an operator:
- `draining` (no new jobs)
- `inactive` (removed from pool)

Reasons include:
- Invalid PoE
- Persistent downtime
- Protocol violations

## 13. Security Model

| Risk | Mitigation |
|------|------------|
| Rogue operator | PoE + signatures |
| Data leakage | Ephemeral execution |
| Fake capacity | Capability verification |
| Central abuse | ENS-based identity |

## 14. Philosophy Alignment

Microscalers are:
- **Trusted**, not anonymous
- **Human**, not abstract
- **Local**, not distant
- **Sovereign**, not rented

This model prioritizes **reliability through people, not capital**.

---

*This Microscaler Onboarding Spec is FINAL for SwarmVision Protocol v0.2.*
*It may be extended in future versions, but MUST remain backward-compatible.*
