# SwarmVision

SwarmVision is a sovereign distributed compute operating system.

## Core Components

- **SwarmAgent** — execution daemon (mining software)
- **SwarmVision OS** — coordination, routing, governance
- **QuantumRails** — model and pipeline builders
- **Microscalers** — trusted local compute operators

## Principles

- No emails, no passwords — ENS + signatures only
- No data storage — execution is ephemeral
- Proof of Execution, not promises
- Pool-based economics — readiness has value
- Human-operated, always-on compute

This repository defines the protocol, reference implementation,
and operational rails for the Swarm.

## Repository Structure

```
swarmvision/
├── docs/
│   ├── manifesto/          # Vision and principles
│   └── architecture/       # Technical design docs
├── swarmvision/
│   ├── os/                 # Core OS coordination
│   ├── identity/           # ENS + signature auth
│   ├── treasury/           # Pool economics
│   └── routing/            # Job routing logic
├── swarmagent/
│   ├── cli/                # Agent CLI tools
│   ├── daemon/             # Execution daemon
│   └── proof/              # Proof of Execution
├── quantumrails/
│   ├── models/             # Model definitions
│   ├── pipelines/          # Pipeline builders
│   └── artifacts/          # Build artifacts
├── infra/
│   ├── docker/             # Container images
│   ├── mesh/               # Network mesh (Tailscale)
│   └── k3s/                # Kubernetes configs
└── scripts/                # Install & ops scripts
```

## Quick Start

```bash
# Install SwarmAgent
curl -fsSL https://swarmvision.io/install.sh | bash

# Register with ENS identity (operators use swarmcompute.eth)
swarmagent register --ens yourname.swarmcompute.eth

# Start earning
swarmagent start
```

## License

MIT
