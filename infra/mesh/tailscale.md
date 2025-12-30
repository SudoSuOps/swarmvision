# Tailscale Mesh Networking

## Overview

SwarmVision uses Tailscale for secure mesh networking between agents.

Tailscale provides:
- Zero-config VPN between agents
- NAT traversal (agents behind firewalls can connect)
- MagicDNS for agent discovery
- ACLs for access control

## Setup

### 1. Create a Tailscale Account

Sign up at https://tailscale.com

### 2. Create an Auth Key

In Tailscale Admin Console:
1. Settings → Keys
2. Generate auth key
3. Enable "Reusable" and "Ephemeral"

### 3. Install on Agent

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate
sudo tailscale up --authkey=tskey-auth-xxxx --hostname=agent-$(hostname)
```

### 4. Verify Connection

```bash
# Check status
tailscale status

# Ping another agent
tailscale ping agent-operator2
```

## SwarmVision Integration

### Agent Discovery

Agents register their Tailscale IP with SwarmVision OS:

```json
{
  "agent_ens": "operator1.swarmcompute.eth",
  "tailscale_ip": "100.x.x.x",
  "tailscale_hostname": "agent-operator1"
}
```

### Direct Agent Communication

For large payloads, agents can communicate directly:

```
Client → SwarmVision OS → Job Assignment
                              ↓
                        SwarmAgent (via Tailscale)
                              ↓
                        Result → Client
```

## ACL Configuration

Example Tailscale ACL for SwarmVision:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:swarmvision-os"],
      "dst": ["tag:swarmagent:*"]
    },
    {
      "action": "accept",
      "src": ["tag:swarmagent"],
      "dst": ["tag:swarmagent:*"]
    }
  ],
  "tagOwners": {
    "tag:swarmvision-os": ["admin@swarmvision.io"],
    "tag:swarmagent": ["admin@swarmvision.io"]
  }
}
```

## Future: Headscale

For fully sovereign operation, consider Headscale (self-hosted Tailscale control server):

```bash
# Deploy Headscale
docker run -d \
  -p 8080:8080 \
  -v /etc/headscale:/etc/headscale \
  headscale/headscale:latest

# Agents connect to your Headscale
tailscale up --login-server=https://headscale.swarmvision.io
```

## Troubleshooting

### Agent Can't Connect

```bash
# Check Tailscale status
tailscale status

# Check if Tailscale is running
systemctl status tailscaled

# Re-authenticate
sudo tailscale up --authkey=tskey-...
```

### Firewall Issues

Tailscale requires outbound UDP/41641 (or HTTPS fallback).

```bash
# Allow Tailscale
sudo ufw allow 41641/udp
```
