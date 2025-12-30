#!/usr/bin/env python3
"""
SwarmVision Protocol — SwarmAgent CLI

The SwarmAgent CLI provides:
- Agent registration and identity management
- Daemon start/stop control
- Status and capability reporting
- Manual proof generation for testing

Usage:
    swarmagent register --ens mynode.swarmcompute.eth
    swarmagent start
    swarmagent status
    swarmagent capabilities
    swarmagent prove --job-id test123 --model-id mock
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from swarmagent.daemon.agent import AgentConfig, SwarmAgent
from swarmagent.proof.execution import HardwareSummary, create_proof


# =============================================================================
# CLI COMMANDS
# =============================================================================

def cmd_register(args):
    """Register agent with ENS identity."""
    config_dir = Path.home() / ".swarmagent"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Validate ENS name
    if not args.ens.endswith(".eth"):
        print("Error: ENS name must end with .eth")
        sys.exit(1)

    # Create or update config
    config = AgentConfig(
        ens_name=args.ens,
        private_key=args.private_key or "",
        coordinator_url=args.coordinator or "http://localhost:8000",
    )

    config.save()

    print(f"Agent registered:")
    print(f"  ENS: {config.ens_name}")
    print(f"  Coordinator: {config.coordinator_url}")
    print(f"  Config: {config_dir / 'config.json'}")
    print()
    print("To start the agent:")
    print("  swarmagent start")


def cmd_start(args):
    """Start the agent daemon."""
    # Load config from file or env
    config_path = Path.home() / ".swarmagent" / "config.json"

    if config_path.exists():
        config = AgentConfig.from_file(config_path)
    else:
        config = AgentConfig.from_env()

    # Override with CLI args
    if args.ens:
        config.ens_name = args.ens
    if args.coordinator:
        config.coordinator_url = args.coordinator

    # Validate
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        print()
        print("Run: swarmagent register --ens yourname.swarmcompute.eth")
        sys.exit(1)

    # Start agent
    print("=" * 50)
    print("SwarmAgent Starting")
    print("=" * 50)

    agent = SwarmAgent(config)

    if args.foreground:
        # Run in foreground
        agent.run_sync()
    else:
        # For now, just run in foreground
        # TODO: Proper daemonization
        print("Running in foreground (use Ctrl+C to stop)")
        print()
        agent.run_sync()


def cmd_stop(args):
    """Stop the agent daemon."""
    # TODO: Implement proper daemon stop via PID file
    print("To stop the agent, use Ctrl+C or kill the process")
    print("Proper daemon management coming soon")


def cmd_status(args):
    """Show agent status."""
    config_path = Path.home() / ".swarmagent" / "config.json"

    if not config_path.exists():
        print("Agent not registered. Run: swarmagent register --ens yourname.eth")
        sys.exit(1)

    config = AgentConfig.from_file(config_path)
    hardware = HardwareSummary.detect()

    print("SwarmAgent Status")
    print("=" * 40)
    print(f"ENS:         {config.ens_name}")
    print(f"Coordinator: {config.coordinator_url}")
    print()
    print("Hardware:")
    print(f"  GPUs:      {hardware.gpu_count}")
    for i, name in enumerate(hardware.gpu_names):
        print(f"    [{i}] {name}")
    print(f"  VRAM:      {hardware.vram_total_gb} GB")
    print(f"  CPU:       {hardware.cpu_cores} cores")
    print(f"  RAM:       {hardware.ram_gb} GB")


def cmd_capabilities(args):
    """Report hardware capabilities."""
    hardware = HardwareSummary.detect()

    output = {
        "gpu_count": hardware.gpu_count,
        "gpu_names": hardware.gpu_names,
        "vram_total_gb": hardware.vram_total_gb,
        "cpu_cores": hardware.cpu_cores,
        "ram_gb": hardware.ram_gb,
        "cuda_version": hardware.cuda_version,
        "driver_version": hardware.driver_version,
        "total_power_draw_w": hardware.total_power_draw_w,
        "total_power_limit_w": hardware.total_power_limit_w,
        "gpus": hardware.gpus,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print("Hardware Capabilities")
        print("=" * 50)
        print(f"CUDA Version:    {hardware.cuda_version or 'N/A'}")
        print(f"Driver Version:  {hardware.driver_version or 'N/A'}")
        print()
        print(f"GPUs: {hardware.gpu_count}")
        if hardware.gpus:
            for gpu in hardware.gpus:
                print(f"  [{gpu['index']}] {gpu['name']}")
                print(f"      VRAM:  {gpu['vram_free_mb']}/{gpu['vram_total_mb']} MB free")
                print(f"      Power: {gpu['power_draw_w']:.1f}/{gpu['power_limit_w']:.0f} W")
                print(f"      Temp:  {gpu['temperature_c']}°C  Util: {gpu['utilization_pct']}%")
                print(f"      Compute: SM {gpu['compute_capability']}")
        else:
            for i, name in enumerate(hardware.gpu_names):
                print(f"  [{i}] {name}")
        print()
        print(f"VRAM Total:      {hardware.vram_total_gb} GB")
        if hardware.gpus:
            avail = hardware.get_available_vram_gb()
            print(f"VRAM Available:  {avail:.2f} GB")
        print(f"Power Draw:      {hardware.total_power_draw_w or 0:.1f} W")
        print(f"Power Limit:     {hardware.total_power_limit_w or 0:.1f} W")
        print()
        print(f"CPU Cores:       {hardware.cpu_cores}")
        print(f"RAM:             {hardware.ram_gb} GB")


def cmd_prove(args):
    """Generate a proof of execution (for testing)."""
    config_path = Path.home() / ".swarmagent" / "config.json"

    if config_path.exists():
        config = AgentConfig.from_file(config_path)
        ens_name = config.ens_name
    else:
        ens_name = args.ens or "test.swarmcompute.eth"

    proof = create_proof(
        agent_ens=ens_name,
        job_id=args.job_id or "test-job-001",
        model_id=args.model_id or "mock-model",
        execution_time_ms=int(args.duration * 1000) if args.duration else 100,
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(proof.to_json())
        print(f"Proof written to: {args.output}")
    else:
        print(proof.to_json())


def cmd_version(args):
    """Show version."""
    print("SwarmAgent v0.2.0")
    print("SwarmVision Protocol Reference Implementation")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="swarmagent",
        description="SwarmVision Agent - Distributed Compute Daemon"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # register
    p_register = subparsers.add_parser("register", help="Register agent identity")
    p_register.add_argument("--ens", required=True, help="ENS name (e.g., mynode.swarmcompute.eth)")
    p_register.add_argument("--private-key", help="Wallet private key (hex)")
    p_register.add_argument("--coordinator", help="SwarmVision OS URL")
    p_register.set_defaults(func=cmd_register)

    # start
    p_start = subparsers.add_parser("start", help="Start agent daemon")
    p_start.add_argument("--ens", help="Override ENS name")
    p_start.add_argument("--coordinator", help="Override coordinator URL")
    p_start.add_argument("--foreground", "-f", action="store_true", help="Run in foreground")
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop agent daemon")
    p_stop.set_defaults(func=cmd_stop)

    # status
    p_status = subparsers.add_parser("status", help="Show agent status")
    p_status.set_defaults(func=cmd_status)

    # capabilities
    p_caps = subparsers.add_parser("capabilities", help="Report hardware capabilities")
    p_caps.add_argument("--json", action="store_true", help="Output as JSON")
    p_caps.set_defaults(func=cmd_capabilities)

    # prove
    p_prove = subparsers.add_parser("prove", help="Generate proof of execution")
    p_prove.add_argument("--ens", help="Agent ENS name")
    p_prove.add_argument("--job-id", help="Job ID")
    p_prove.add_argument("--model-id", help="Model ID")
    p_prove.add_argument("--duration", type=float, help="Simulated duration in seconds")
    p_prove.add_argument("--output", "-o", help="Output file path")
    p_prove.set_defaults(func=cmd_prove)

    # version
    p_version = subparsers.add_parser("version", help="Show version")
    p_version.set_defaults(func=cmd_version)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
