# SwarmVision Architecture Overview

## System Components

SwarmVision consists of four primary components:

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                  │
│              (Submit jobs, consume compute)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SWARMVISION OS                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │  Identity   │ │   Router    │ │  Treasury   │ │    API     │ │
│  │   (ENS)     │ │  (Jobs)     │ │  (Credits)  │ │  (REST)    │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SWARMAGENT                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │    CLI      │ │   Daemon    │ │   Proof     │ │  Executor  │ │
│  │  (Control)  │ │ (Heartbeat) │ │ (Signing)   │ │  (Models)  │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      QUANTUMRAILS                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │   Models    │ │  Pipelines  │ │  Artifacts  │                │
│  │ (Weights)   │ │  (Graphs)   │ │  (Outputs)  │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. SwarmAgent

**Purpose:** Execution daemon running on operator hardware.

**Location:** `swarmagent/`

### Components

| Component | File | Description |
|-----------|------|-------------|
| CLI | `cli/main.py` | Command-line interface for operators |
| Daemon | `daemon/agent.py` | Background service handling jobs |
| Proof | `proof/execution.py` | Proof of Execution generation |

### Lifecycle

```
1. REGISTER    →  swarmagent register --ens operator.swarmagent.eth
2. START       →  swarmagent start (daemon mode)
3. HEARTBEAT   →  Every 30s: report status to SwarmVision OS
4. POLL        →  Every 5s: check for available jobs
5. EXECUTE     →  Run job, produce result
6. PROVE       →  Generate Proof of Execution
7. SUBMIT      →  Send proof to SwarmVision OS
8. EARN        →  Receive credits for verified work
```

### Configuration

```bash
# Environment variables
SWARMAGENT_ENS=mynode.swarmagent.eth
SWARMAGENT_PRIVATE_KEY=0x...
SWARMVISION_URL=http://swarmvision.io:8000

# Or config file: ~/.swarmagent/config.json
```

---

## 2. SwarmVision OS

**Purpose:** Coordination layer for the distributed compute network.

**Location:** `swarmvision/`

### Components

| Component | File | Description |
|-----------|------|-------------|
| Core | `os/core.py` | FastAPI application, main endpoints |
| Identity | `identity/ens.py` | ENS resolution and verification |
| Router | `routing/router.py` | Job assignment and load balancing |
| Treasury | `treasury/pool.py` | Credit accounting and payments |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agent/heartbeat` | POST | Receive agent heartbeat |
| `/agent/jobs` | GET | Poll for available jobs |
| `/job/submit` | POST | Submit a new job |
| `/job/{id}` | GET | Get job status |
| `/proof/submit` | POST | Submit proof of execution |
| `/account/{ens}` | GET | Get account balance |
| `/stats` | GET | System statistics |

### Job Flow

```
CLIENT                    SWARMVISION OS                 SWARMAGENT
   │                            │                            │
   │──── POST /job/submit ─────>│                            │
   │<─── job_id ────────────────│                            │
   │                            │                            │
   │                            │<── GET /agent/jobs ────────│
   │                            │─── job details ───────────>│
   │                            │                            │
   │                            │                      [EXECUTE]
   │                            │                            │
   │                            │<── POST /proof/submit ─────│
   │                            │─── payment confirmed ─────>│
   │                            │                            │
   │──── GET /job/{id} ────────>│                            │
   │<─── status: completed ─────│                            │
```

---

## 3. QuantumRails

**Purpose:** Model and pipeline management for AI workloads.

**Location:** `quantumrails/`

### Components

| Directory | Purpose |
|-----------|---------|
| `models/` | Model definitions and weights |
| `pipelines/` | Execution pipeline definitions |
| `artifacts/` | Build outputs and cached results |

### Integration

QuantumRails defines WHAT gets executed.
SwarmAgent handles HOW it gets executed.
SwarmVision OS coordinates WHERE it gets executed.

---

## 4. Microscalers

**Definition:** Human operators running SwarmAgent on their own hardware.

### Requirements

- GPU with 8GB+ VRAM (recommended)
- Stable internet connection
- ENS name for identity
- Wallet for signatures

### Economics

```
JOB_COST = 10 credits
OPERATOR_SHARE = 90%  (9 credits to operator)
PROTOCOL_FEE = 10%    (1 credit to protocol)
```

---

## Proof of Execution

The core primitive of SwarmVision.

### Structure

```json
{
  "agent_ens": "operator1.swarmagent.eth",
  "job_id": "job_abc123",
  "hardware": {
    "gpu_count": 2,
    "gpu_names": ["RTX 4090", "RTX 4090"],
    "vram_total_gb": 48.0,
    "cpu_cores": 32,
    "ram_gb": 128.0
  },
  "model_id": "swarmhealth-diabetes-v3",
  "start_time": "2024-01-15T10:30:00Z",
  "end_time": "2024-01-15T10:30:05Z",
  "result_hash": "sha256:abc123...",
  "signature": "0x..."
}
```

### Verification

1. Signature matches agent's registered public key
2. Timestamps are reasonable
3. Hardware matches agent's registered capabilities
4. Result hash is non-empty

---

## Networking

### Current (v0.1)

- Direct HTTP connections
- SwarmVision OS as central coordinator
- Agents poll for jobs

### Future

- Tailscale mesh for agent-to-agent
- Multiple coordinators for redundancy
- Push-based job assignment

### Tailscale Integration

```bash
# Agents join the swarm mesh
tailscale up --authkey=tskey-... --hostname=agent-$ENS

# Access via Tailscale DNS
curl http://agent-operator1.swarm.ts.net/status
```

---

## Deployment

### Docker

```bash
# Build images
docker build -f infra/docker/Dockerfile.swarmvision -t swarmvision:latest .
docker build -f infra/docker/Dockerfile.swarmagent -t swarmagent:latest .

# Run SwarmVision OS
docker run -d -p 8000:8000 swarmvision:latest

# Run SwarmAgent
docker run -d \
  -e SWARMAGENT_ENS=mynode.swarmagent.eth \
  -e SWARMVISION_URL=http://host.docker.internal:8000 \
  --gpus all \
  swarmagent:latest
```

### Bare Metal

```bash
# SwarmVision OS
cd swarmvision
pip install -r requirements.txt
python -m swarmvision.os.core

# SwarmAgent
curl -fsSL https://swarmvision.io/install.sh | bash
swarmagent register --ens mynode.swarmagent.eth
swarmagent start
```

---

## Security Model

### Trust Assumptions

1. **SwarmVision OS** — Trusted coordinator (centralized in v0.1)
2. **SwarmAgents** — Semi-trusted (verified via proofs)
3. **Clients** — Untrusted (must prepay)

### Threat Mitigations

| Threat | Mitigation |
|--------|------------|
| Fake proofs | Cryptographic signatures |
| Payment fraud | Prepaid credits |
| Identity spoofing | ENS + wallet signatures |
| Data leakage | Ephemeral execution |

---

## Roadmap

### v0.1 (Current)

- [x] SwarmAgent daemon
- [x] SwarmVision OS coordinator
- [x] Proof of Execution
- [x] Credit-based treasury
- [x] Mock ENS resolution

### v0.2

- [ ] Real ENS integration
- [ ] ECDSA proof signatures
- [ ] Persistent job history
- [ ] Agent reputation scores

### v0.3

- [ ] On-chain treasury
- [ ] Multi-coordinator failover
- [ ] Model routing intelligence
- [ ] Geographic awareness

### v1.0

- [ ] Full decentralization
- [ ] DAO governance
- [ ] Token economics
- [ ] Production hardening

---

*SwarmVision Protocol — Building the sovereign compute layer.*
