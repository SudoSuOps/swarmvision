# SwarmVision Mesh Networking

> **Protocol Version:** v0.2
> **Status:** Reference Architecture

## Design Philosophy: Mesh-First

SwarmVision assumes **no public ports**. All agents operate behind NAT, firewalls, or
residential networks. The network layer is built on encrypted mesh VPNs.

This is intentional:
- **Security**: No exposed attack surface
- **Privacy**: Operators don't reveal their IP addresses
- **Simplicity**: No port forwarding, no DDNS, no firewall rules
- **Resilience**: Mesh networks self-heal and route around failures

## Supported Mesh Technologies

### Tailscale (Recommended for Getting Started)

[Tailscale](https://tailscale.com) provides the easiest path to mesh networking:

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Connect to your tailnet
sudo tailscale up

# Verify connectivity
tailscale status
```

**Pros:**
- Zero configuration
- Free tier for personal use (100 devices)
- Automatic NAT traversal
- Built-in MagicDNS

**Cons:**
- Requires Tailscale account
- Control plane is hosted by Tailscale

### Headscale (Self-Hosted Control Plane)

[Headscale](https://github.com/juanfont/headscale) is an open-source implementation
of the Tailscale control plane:

```bash
# Run Headscale server
docker run -d \
  --name headscale \
  -v /path/to/config:/etc/headscale \
  -v /path/to/data:/var/lib/headscale \
  -p 8080:8080 \
  headscale/headscale:latest

# Connect agents
tailscale up --login-server https://headscale.yourdomain.com
```

**Pros:**
- Full sovereignty - you control the control plane
- No external dependencies
- Can run on SwarmVision OS coordinator

**Cons:**
- Requires server with public IP for control plane
- More setup complexity

### WireGuard (Manual Configuration)

For advanced users, raw WireGuard provides maximum control:

```ini
# /etc/wireguard/swarm.conf
[Interface]
PrivateKey = <agent_private_key>
Address = 10.42.0.X/24
ListenPort = 51820

[Peer]
PublicKey = <coordinator_public_key>
Endpoint = coordinator.swarmvision.io:51820
AllowedIPs = 10.42.0.0/24
PersistentKeepalive = 25
```

**Pros:**
- No external services required
- Maximum performance
- Full control over routing

**Cons:**
- Manual key exchange
- Complex multi-peer setup
- No automatic NAT traversal

## Network Architecture

```
                    ┌─────────────────┐
                    │   Internet      │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │     Mesh Control Plane      │
              │  (Tailscale/Headscale/WG)   │
              └──────────────┬──────────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
┌──────┴──────┐       ┌──────┴──────┐       ┌──────┴──────┐
│ SwarmVision │       │ SwarmAgent  │       │ SwarmAgent  │
│     OS      │       │   Node 1    │       │   Node 2    │
│ (Coordinator)│       │  (GPU Rig)  │       │  (GPU Rig)  │
└─────────────┘       └─────────────┘       └─────────────┘
  100.x.x.1             100.x.x.10            100.x.x.11
```

All communication happens over the mesh network using internal IPs.
No public ports are exposed.

## SwarmAgent Configuration

### With Tailscale

```yaml
# ~/.swarmagent/config.yaml
coordinator_url: http://100.x.x.1:8000  # Tailscale IP
mesh:
  type: tailscale
  network_name: swarm
```

### With Headscale

```yaml
coordinator_url: http://coordinator.swarm.internal:8000
mesh:
  type: headscale
  control_server: https://headscale.yourdomain.com
```

### With WireGuard

```yaml
coordinator_url: http://10.42.0.1:8000
mesh:
  type: wireguard
  interface: swarm0
  config_path: /etc/wireguard/swarm.conf
```

## Security Model

### Traffic Flow

1. **Agent ↔ Coordinator**: All API calls over mesh (encrypted)
2. **Agent ↔ Agent**: Not currently supported (future: direct job relay)
3. **External Access**: Blocked by default

### Authentication Layers

1. **Mesh Layer**: WireGuard encryption (Curve25519, ChaCha20-Poly1305)
2. **Identity Layer**: ENS name + wallet signature
3. **Proof Layer**: ECDSA signatures on execution proofs

### Threat Model

| Threat | Mitigation |
|--------|------------|
| Network scanning | No public ports |
| Man-in-the-middle | WireGuard encryption |
| Replay attacks | Timestamp validation (5 min window) |
| Identity spoofing | Wallet signatures |
| Proof forgery | ECDSA on proof hash |

## Deployment Patterns

### Pattern 1: Personal Tailnet

For individual operators or small teams:

```
You → Tailscale Account → Your Devices
```

- Single operator runs SwarmVision OS + agents on personal machines
- Uses Tailscale free tier
- MagicDNS for service discovery

### Pattern 2: Shared Headscale

For collectives or DAOs:

```
DAO → Self-hosted Headscale → Member Devices
```

- DAO runs Headscale on a VPS
- Members connect their GPU rigs
- Full sovereignty, no external dependencies

### Pattern 3: Hybrid

For production deployments:

```
Public Coordinator (API) ←→ Private Mesh (Compute)
```

- SwarmVision OS has a public API endpoint (for clients)
- Agent mesh is private (Tailscale/Headscale)
- Coordinator bridges public and private networks

## DNS and Service Discovery

### MagicDNS (Tailscale)

Tailscale provides automatic DNS:

```bash
# Access coordinator by machine name
curl http://swarmvision-os:8000/health

# Or by tailnet name
curl http://swarmvision-os.tail12345.ts.net:8000/health
```

### Headscale DNS

Configure Headscale with custom DNS:

```yaml
# headscale config
dns_config:
  nameservers:
    - 1.1.1.1
  domains: []
  magic_dns: true
  base_domain: swarm.internal
```

### Static Configuration

For WireGuard or when DNS is unavailable:

```yaml
# ~/.swarmagent/config.yaml
coordinator_url: http://10.42.0.1:8000
```

## Firewall Rules

### Agent Nodes

No incoming ports required. Outbound only:

```bash
# Tailscale (UDP hole-punching)
iptables -A OUTPUT -p udp --dport 41641 -j ACCEPT

# HTTPS for control plane
iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
```

### Coordinator Node

No public ports for SwarmVision OS:

```bash
# Only listen on mesh interface
uvicorn swarmvision.os.core:app --host 100.x.x.1 --port 8000
```

## Troubleshooting

### Agent Can't Reach Coordinator

1. Verify mesh connectivity:
   ```bash
   tailscale ping coordinator-hostname
   ```

2. Check mesh status:
   ```bash
   tailscale status
   ```

3. Verify coordinator is listening on mesh IP:
   ```bash
   curl http://100.x.x.1:8000/health
   ```

### Slow Job Transfers

1. Check for relay vs direct:
   ```bash
   tailscale status --peers
   # Look for "relay" vs "direct"
   ```

2. Enable direct connections:
   ```bash
   # On both nodes
   sudo tailscale up --accept-routes
   ```

### Headscale Control Plane Issues

1. Check Headscale logs:
   ```bash
   docker logs headscale
   ```

2. Verify node registration:
   ```bash
   headscale nodes list
   ```

## Future Considerations

- **Direct Agent-to-Agent**: Relay large payloads directly between agents
- **Multi-Region Mesh**: Federated Headscale instances
- **Zero-Trust Overlay**: Additional encryption layer for sensitive workloads
- **Mesh Health Monitoring**: Automatic failover and re-routing

---

*This document describes the mesh-first networking architecture for SwarmVision Protocol v0.2.*
