#!/usr/bin/env python3
"""
SwarmView CLI — Client Interface for SwarmVision Protocol

Bee-1 (Client) submits jobs to SwarmVision OS, polls for completion,
downloads result artifacts, and verifies Proof of Execution.

Usage:
    swarmview submit --task swarmview.mri.demo --input ./scan.json --out ./report.pdf
    swarmview status --job-id job_xxx
    swarmview verify --job-id job_xxx
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from swarmvision.identity.signing import canonical_json_bytes, sha256_hex
from swarmvision.identity.ethsig import recover_eip191_address


# =============================================================================
# CONFIGURATION
# =============================================================================

def get_config() -> dict:
    """Load client configuration from environment."""
    return {
        "ens_name": os.environ.get("SWARMVIEW_ENS", "swarmview.swarmvision.eth"),
        "private_key": os.environ.get("SWARMVIEW_PRIVATE_KEY", ""),
        "coordinator_url": os.environ.get("SWARMVISION_URL", "http://localhost:8000"),
    }


# =============================================================================
# API CLIENT
# =============================================================================

class SwarmViewClient:
    """Client for interacting with SwarmVision OS."""

    def __init__(self, coordinator_url: str, ens_name: str):
        self.coordinator_url = coordinator_url.rstrip("/")
        self.ens_name = ens_name

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        """Make HTTP request to coordinator."""
        url = f"{self.coordinator_url}{path}"

        if data:
            body = json.dumps(data).encode("utf-8")
            headers = {"Content-Type": "application/json"}
        else:
            body = None
            headers = {}

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise RuntimeError(f"HTTP {e.code}: {error_body}")

    def deposit(self, amount: int) -> dict:
        """Deposit credits to account."""
        return self._request("POST", f"/account/{self.ens_name}/deposit?amount={amount}")

    def submit_job(self, task: str, payload: dict) -> dict:
        """Submit a job for execution."""
        return self._request("POST", "/job/submit", {
            "client_ens": self.ens_name,
            "model_id": task,
            "payload": payload,
        })

    def get_job_status(self, job_id: str) -> dict:
        """Get job status."""
        return self._request("GET", f"/job/{job_id}")

    def get_job_result(self, job_id: str) -> bytes:
        """Download job result artifact."""
        url = f"{self.coordinator_url}/job/{job_id}/result"
        req = urllib.request.Request(url, method="GET")

        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    def get_job_poe(self, job_id: str) -> dict:
        """Get Proof of Execution for job."""
        return self._request("GET", f"/job/{job_id}/poe")

    def verify_poe(self, poe: dict) -> bool:
        """Verify a Proof of Execution."""
        # Extract signature block
        sig_block = poe.get("signature")
        if not sig_block:
            return False

        # Reconstruct payload without signature
        poe_copy = {k: v for k, v in poe.items() if k != "signature"}

        # Compute expected hash
        b = canonical_json_bytes(poe_copy)
        expected_hash = sha256_hex(b)

        # Check message hash matches
        if sig_block.get("message_hash") != expected_hash:
            print(f"  Hash mismatch: expected {expected_hash[:16]}...")
            return False

        # Recover signer
        try:
            recovered = recover_eip191_address(
                sig_block["message_hash"],
                sig_block["signature"]
            )
        except Exception as e:
            print(f"  Signature recovery failed: {e}")
            return False

        # Check signer matches operator wallet
        claimed = poe.get("operator", {}).get("wallet", {}).get("address", "").lower()
        if recovered != claimed:
            print(f"  Signer mismatch: {recovered} != {claimed}")
            return False

        return True


# =============================================================================
# CLI COMMANDS
# =============================================================================

def cmd_submit(args):
    """Submit a job and wait for result."""
    config = get_config()
    client = SwarmViewClient(config["coordinator_url"], config["ens_name"])

    # Load input
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input file not found: {args.input}")
            sys.exit(1)
        with open(input_path) as f:
            payload = json.load(f)
    else:
        payload = {}

    # Add task-specific metadata
    payload["_task"] = args.task
    payload["_client_ens"] = config["ens_name"]

    print(f"SwarmView Submit")
    print("=" * 50)
    print(f"Client:      {config['ens_name']}")
    print(f"Coordinator: {config['coordinator_url']}")
    print(f"Task:        {args.task}")
    print()

    # Ensure we have credits
    try:
        client.deposit(1000)
        print("[+] Deposited 1000 credits")
    except Exception as e:
        print(f"[!] Deposit failed (may already have balance): {e}")

    # Submit job
    try:
        result = client.submit_job(args.task, payload)
        job_id = result["job_id"]
        print(f"[+] Job submitted: {job_id}")
    except Exception as e:
        print(f"[-] Submit failed: {e}")
        sys.exit(1)

    # Poll for completion
    print()
    print("Waiting for completion...")
    max_wait = args.timeout or 120
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            status = client.get_job_status(job_id)
            job_status = status.get("status", "unknown")

            if job_status == "completed":
                print(f"[+] Job completed!")
                break
            elif job_status == "failed":
                print(f"[-] Job failed")
                sys.exit(1)
            else:
                elapsed = int(time.time() - start_time)
                print(f"    Status: {job_status} ({elapsed}s)", end="\r")
                time.sleep(2)
        except Exception as e:
            print(f"    Poll error: {e}")
            time.sleep(2)
    else:
        print(f"[-] Timeout waiting for job completion")
        sys.exit(1)

    # Download result
    print()
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result_data = client.get_job_result(job_id)
            with open(out_path, "wb") as f:
                f.write(result_data)
            print(f"[+] Result saved: {out_path} ({len(result_data)} bytes)")
        except Exception as e:
            print(f"[-] Failed to download result: {e}")

    # Verify PoE
    if args.verify:
        print()
        print("Verifying Proof of Execution...")
        try:
            poe = client.get_job_poe(job_id)
            if client.verify_poe(poe):
                print("[+] PoE verified successfully")
                print(f"    Operator: {poe.get('operator', {}).get('operator_ens', 'unknown')}")
                print(f"    Result hash: {poe.get('result', {}).get('result_hash', 'unknown')[:16]}...")
            else:
                print("[-] PoE verification failed")
        except Exception as e:
            print(f"[-] Could not retrieve PoE: {e}")

    print()
    print("=" * 50)
    print("Done.")


def cmd_status(args):
    """Check job status."""
    config = get_config()
    client = SwarmViewClient(config["coordinator_url"], config["ens_name"])

    try:
        status = client.get_job_status(args.job_id)
        print(json.dumps(status, indent=2))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_verify(args):
    """Verify job PoE."""
    config = get_config()
    client = SwarmViewClient(config["coordinator_url"], config["ens_name"])

    try:
        poe = client.get_job_poe(args.job_id)
        print("Proof of Execution:")
        print(json.dumps(poe, indent=2))
        print()

        if client.verify_poe(poe):
            print("VERIFIED: PoE is valid")
        else:
            print("INVALID: PoE verification failed")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_account(args):
    """Show account info."""
    config = get_config()
    client = SwarmViewClient(config["coordinator_url"], config["ens_name"])

    try:
        info = client._request("GET", f"/account/{config['ens_name']}")
        print(f"Account: {config['ens_name']}")
        print("=" * 40)
        print(f"Balance:        {info.get('balance', 0)} credits")
        print(f"Total earned:   {info.get('total_earned', 0)}")
        print(f"Total spent:    {info.get('total_spent', 0)}")
        print(f"Jobs submitted: {info.get('jobs_submitted', 0)}")
        print(f"Jobs completed: {info.get('jobs_completed', 0)}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="swarmview",
        description="SwarmView — Client Interface for SwarmVision Protocol"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # submit
    p_submit = subparsers.add_parser("submit", help="Submit a job")
    p_submit.add_argument("--task", required=True, help="Task name (e.g., swarmview.mri.demo)")
    p_submit.add_argument("--input", "-i", help="Input JSON file")
    p_submit.add_argument("--out", "-o", help="Output file path for result")
    p_submit.add_argument("--timeout", "-t", type=int, default=120, help="Max wait time (seconds)")
    p_submit.add_argument("--verify", "-v", action="store_true", help="Verify PoE after completion")
    p_submit.set_defaults(func=cmd_submit)

    # status
    p_status = subparsers.add_parser("status", help="Check job status")
    p_status.add_argument("--job-id", required=True, help="Job ID")
    p_status.set_defaults(func=cmd_status)

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify job PoE")
    p_verify.add_argument("--job-id", required=True, help="Job ID")
    p_verify.set_defaults(func=cmd_verify)

    # account
    p_account = subparsers.add_parser("account", help="Show account info")
    p_account.set_defaults(func=cmd_account)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
