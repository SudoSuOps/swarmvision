# Proof of Execution — Canonical Signing Rule

> **Protocol Version:** v0.2
> **Status:** LOCKED — No changes without major version bump.

## Signing Algorithm

### Step 1: Remove Signature Block

Before signing, remove the `signature` object entirely from the PoE.

```python
poe_data = { ... }  # Full PoE
del poe_data["signature"]
```

### Step 2: Canonicalize JSON

Serialize to canonical JSON with these rules:

| Rule | Value |
|------|-------|
| Encoding | UTF-8 |
| Key order | Sorted (recursive) |
| Whitespace | None (compact) |
| Separators | `,` and `:` (no spaces) |

```python
import json

canonical_json = json.dumps(
    poe_data,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False
).encode("utf-8")
```

### Step 3: Compute Message Hash

```python
import hashlib

message_hash = hashlib.sha256(canonical_json).hexdigest()
```

### Step 4: Sign with Operator Wallet

Sign `message_hash` using EIP-191 (personal_sign) or EIP-712:

```python
# EIP-191 personal sign
from eth_account.messages import encode_defunct
from eth_account import Account

message = encode_defunct(text=message_hash)
signed = Account.sign_message(message, private_key)
signature = signed.signature.hex()
```

### Step 5: Reattach Signature Block

```python
poe_data["signature"] = {
    "scheme": "eip191",
    "message_hash": message_hash,
    "signature": signature
}
```

## Verification

To verify a PoE:

1. Extract and remove `signature` block
2. Canonicalize remaining JSON (same rules)
3. Compute `sha256(canonical_json)`
4. Verify computed hash matches `signature.message_hash`
5. Recover signer address from signature
6. Verify signer matches `operator.wallet.address`

```python
def verify_poe(poe: dict) -> bool:
    sig_block = poe.pop("signature")

    # Canonicalize
    canonical = json.dumps(poe, sort_keys=True, separators=(",", ":"))
    computed_hash = hashlib.sha256(canonical.encode()).hexdigest()

    # Verify hash
    if computed_hash != sig_block["message_hash"]:
        return False

    # Recover signer
    from eth_account.messages import encode_defunct
    from eth_account import Account

    message = encode_defunct(text=computed_hash)
    recovered = Account.recover_message(message, signature=sig_block["signature"])

    # Verify address
    return recovered.lower() == poe["operator"]["wallet"]["address"].lower()
```

## Guarantees

| Property | Guarantee |
|----------|-----------|
| Deterministic | Same PoE always produces same hash |
| Cross-language | UTF-8 + sorted keys = universal |
| Replay-safe | poe_id + timestamps prevent replay |
| Tamper-evident | Any modification invalidates signature |

## Reference Implementation

See: `swarmvision/identity/crypto.py`

---

# Minimal Valid PoE Example

```json
{
  "protocol": { "name": "swarmvision", "version": "0.2" },
  "poe_id": "01J9Z8Q3Y4W1K8F0A9D2M6C5B7",
  "job": {
    "job_id": "job-123",
    "client_ens": "xyzmed.swarmvision.eth",
    "task": "wholeBrainSeg",
    "received_at": "2025-01-15T02:10:00Z",
    "pricing": { "currency": "USD", "unit_price": "0.10", "unit": "scan" }
  },
  "operator": {
    "operator_ens": "rig42.swarmcompute.eth",
    "wallet": { "chain": "eip155:1", "address": "0xabc123abc123abc123abc123abc123abc123abcd" },
    "agent": { "name": "swarmagent", "version": "0.2.0", "build": "git:deadbeef" }
  },
  "execution": {
    "started_at": "2025-01-15T02:10:01Z",
    "ended_at": "2025-01-15T02:10:05Z",
    "duration_ms": 4000,
    "host": { "hostname": "rig42", "os": "linux", "arch": "x86_64" },
    "resources": {
      "cpu": { "model": "Ryzen 7950X", "cores": 16 },
      "memory": { "ram_bytes": 68719476736 },
      "gpus": [
        { "index": 0, "vendor": "nvidia", "model": "RTX 5090", "vram_bytes": 34359738368, "driver": "550.40" }
      ]
    }
  },
  "artifact": { "artifact_id": "vista3d-v1", "type": "model", "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },
  "result": { "status": "success", "result_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" },
  "attestations": { "ephemeral_execution": true },
  "signature": {
    "scheme": "eip191",
    "message_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "signature": "0xdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  }
}
```

---

*This document is LOCKED as of SwarmVision Protocol v0.2.*
*No breaking changes without major version bump.*
