# SwarmVision Identity Rules

> **Protocol Version:** v0.2
> **Status:** FROZEN — No breaking changes after this version.

## ENS Namespaces

SwarmVision uses ENS (Ethereum Name Service) for identity.
Namespaces are separated by role to ensure clear accountability.

### Operator Namespace: `*.swarmcompute.eth`

**Who:** Compute operators running SwarmAgent daemons.

**Format:** `<name>.swarmcompute.eth`

**Examples:**
- `rig42.swarmcompute.eth`
- `datacenter-west.swarmcompute.eth`
- `homelab.swarmcompute.eth`

**Permissions:**
- Receive job assignments
- Execute jobs
- Submit Proofs of Execution
- Earn credits for completed work

**Requirements:**
- Must have valid Ethereum wallet
- Must run SwarmAgent daemon
- Must maintain heartbeat (every 30s)

### Client Namespace: `*.swarmvision.eth`

**Who:** Clients who submit jobs and consume compute.

**Format:** `<name>.swarmvision.eth`

**Examples:**
- `myapp.swarmvision.eth`
- `research-lab.swarmvision.eth`
- `startup.swarmvision.eth`

**Permissions:**
- Submit jobs
- Check job status
- Receive results
- Spend credits

**Requirements:**
- Must have valid Ethereum wallet
- Must maintain positive credit balance

### Generic ENS: `*.eth`

**Who:** Any ENS name not in the above namespaces.

**Default Role:** CLIENT

**Examples:**
- `vitalik.eth`
- `mycompany.eth`

**Notes:**
- Treated as clients by default
- Cannot operate as agents
- Full client permissions

## Identity Verification

### Wallet Signature (v0.2)

All authenticated requests must include:

```
Authorization: Bearer <signature>
X-ENS-Name: <ens_name>
X-Timestamp: <unix_timestamp>
```

Signature is ECDSA over:
```
message = keccak256(abi.encodePacked(ens_name, timestamp, request_path))
```

### ENS Resolution

1. Resolve ENS name to Ethereum address
2. Verify signature was produced by that address
3. Check role from namespace
4. Grant appropriate permissions

## Role Matrix

| Action | OPERATOR | CLIENT |
|--------|----------|--------|
| Submit job | ❌ | ✅ |
| Receive job assignment | ✅ | ❌ |
| Execute job | ✅ | ❌ |
| Submit proof | ✅ | ❌ |
| Check job status | ✅ (own jobs) | ✅ (own jobs) |
| Deposit credits | ❌ | ✅ |
| Earn credits | ✅ | ❌ |
| Withdraw credits | ✅ | ✅ |

## Security Considerations

1. **Namespace Separation:** Operators cannot submit jobs; clients cannot execute jobs.
2. **Wallet Binding:** ENS names are bound to Ethereum addresses.
3. **Signature Freshness:** Timestamps prevent replay attacks (5 minute window).
4. **Proof Verification:** All proofs are cryptographically signed by operators.

## Future Considerations (Post v0.2)

- On-chain ENS subdomain registration
- Reputation scores per identity
- Stake requirements for operators
- Rate limiting per identity
- Identity delegation/proxies

---

*This document defines identity rules for SwarmVision Protocol v0.2.*
*No breaking changes will be made to these rules without a major version bump.*
