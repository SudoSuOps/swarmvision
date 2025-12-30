#!/usr/bin/env python3
"""
SwarmView End-to-End Flow Test (Python version)

Tests the complete execution path without requiring separate processes.
"""

import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from swarmvision.os.core import (
    app, get_router, get_treasury, get_epoch_state, reset_epoch_state,
    _job_results, _job_poes,
)
from swarmvision.identity.ens import get_identity_service
from swarmvision.identity.crypto import private_key_to_address
from swarmvision.identity.signing import canonical_json_bytes, sha256_hex
from swarmvision.identity.ethsig import sign_eip191_hash
from swarmview.tasks.mri_demo import execute_mri_demo
from swarmagent.daemon.agent import SwarmAgent, AgentConfig, JobExecutor, Job


# Test keys
CLIENT_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
OPERATOR_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
SIGNER_KEY = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"

# Identities
CLIENT_ENS = "swarmview.swarmvision.eth"
OPERATOR_ENS = "rig1.swarmcompute.eth"


def setup_identities():
    """Register test identities."""
    ens = get_identity_service()

    client_addr = private_key_to_address(CLIENT_KEY)
    operator_addr = private_key_to_address(OPERATOR_KEY)

    ens.register(CLIENT_ENS, client_addr, "client")
    ens.register(OPERATOR_ENS, operator_addr, "operator")

    print(f"Registered client: {CLIENT_ENS} -> {client_addr}")
    print(f"Registered operator: {OPERATOR_ENS} -> {operator_addr}")

    return client_addr, operator_addr


def test_mri_demo_task():
    """Test MRI demo task execution."""
    print("\n=== Test: MRI Demo Task ===")

    payload = {
        "patient_id": "TEST-001",
        "scan_type": "Brain MRI T1-weighted",
        "_client_ens": CLIENT_ENS,
    }

    pdf_bytes, analysis = execute_mri_demo(
        job_payload=payload,
        operator_ens=OPERATOR_ENS,
        job_id="job_test001",
    )

    print(f"  PDF generated: {len(pdf_bytes)} bytes")
    print(f"  Risk: {analysis['severity']} ({analysis['risk_score']:.1%})")
    print(f"  Findings: {len(analysis['findings'])}")

    # Verify PDF format
    assert pdf_bytes[:4] == b'%PDF', "Invalid PDF format"
    print("  PDF format: VALID")

    return pdf_bytes, analysis


def test_job_submission():
    """Test job submission to SwarmVision OS."""
    print("\n=== Test: Job Submission ===")

    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Deposit credits
    resp = client.post(f"/account/{CLIENT_ENS}/deposit?amount=1000")
    assert resp.status_code == 200
    print(f"  Deposited 1000 credits")

    # Submit job
    resp = client.post("/job/submit", json={
        "client_ens": CLIENT_ENS,
        "model_id": "swarmview.mri.demo",
        "payload": {"patient_id": "TEST-002", "scan_type": "Brain MRI"},
    })
    assert resp.status_code == 200
    job_data = resp.json()
    job_id = job_data["job_id"]
    print(f"  Job submitted: {job_id}")

    # Check job status
    resp = client.get(f"/job/{job_id}")
    assert resp.status_code == 200
    status = resp.json()
    print(f"  Job status: {status['status']}")

    return job_id


def test_agent_execution(job_id: str):
    """Test SwarmAgent job execution."""
    print("\n=== Test: Agent Execution ===")

    # Create executor
    executor = JobExecutor(OPERATOR_ENS, OPERATOR_KEY)

    # Create job object
    job = Job(
        job_id=job_id,
        model_id="swarmview.mri.demo",
        payload={"patient_id": "TEST-002", "scan_type": "Brain MRI", "_client_ens": CLIENT_ENS},
        submitted_at="2025-01-01T00:00:00Z",
        client_ens=CLIENT_ENS,
    )

    # Execute
    proof = executor.execute(job)
    print(f"  Proof generated: {proof.job_id}")
    print(f"  Result hash: {proof.result_hash[:16]}...")

    # Get result
    result_data = executor.get_result(job_id)
    assert result_data is not None
    print(f"  Result: {len(result_data)} bytes")

    return proof, result_data


def test_result_upload(job_id: str, result_data: bytes):
    """Test result upload to SwarmVision OS."""
    print("\n=== Test: Result Upload ===")

    import base64
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Upload result
    resp = client.post(f"/job/{job_id}/result", json={
        "job_id": job_id,
        "data": base64.b64encode(result_data).decode(),
        "content_type": "application/pdf",
    })
    assert resp.status_code == 200
    print(f"  Uploaded: {len(result_data)} bytes")

    # Download result
    resp = client.get(f"/job/{job_id}/result")
    assert resp.status_code == 200
    downloaded = resp.content
    assert downloaded == result_data
    print(f"  Downloaded: {len(downloaded)} bytes")
    print(f"  Integrity: {'MATCH' if downloaded == result_data else 'MISMATCH'}")

    return True


def test_poe_submission(job_id: str, result_data: bytes):
    """Test v0.2 PoE submission."""
    print("\n=== Test: PoE Submission ===")

    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Compute result hash
    result_hash = hashlib.sha256(result_data).hexdigest()
    operator_addr = private_key_to_address(OPERATOR_KEY)

    # Build PoE
    poe_dict = {
        "protocol": {"name": "swarmvision", "version": "0.2"},
        "poe_id": f"poe_{job_id}",
        "job": {
            "job_id": job_id,
            "client_ens": CLIENT_ENS,
            "task": "swarmview.mri.demo",
            "received_at": "2025-01-01T00:00:00Z",
            "pricing": {"currency": "USD", "unit_price": "10.00", "unit": "job"},
        },
        "operator": {
            "operator_ens": OPERATOR_ENS,
            "wallet": {"chain": "ethereum", "address": operator_addr},
            "agent": {"version": "0.2.0"},
        },
        "execution": {
            "started_at": "2025-01-01T00:00:00Z",
            "ended_at": "2025-01-01T00:00:05Z",
            "duration_ms": 5000,
            "host": {"hostname": "test-host"},
            "resources": {"gpus": []},
        },
        "artifact": {
            "artifact_id": f"art_{job_id}",
            "type": "pdf",
            "hash": result_hash,
        },
        "result": {
            "status": "success",
            "result_hash": result_hash,
        },
        "attestations": {},
    }

    # Sign PoE
    b = canonical_json_bytes(poe_dict)
    h = sha256_hex(b)
    sig = sign_eip191_hash(h, OPERATOR_KEY)

    poe_dict["signature"] = {
        "scheme": "eip191",
        "message_hash": h,
        "signature": sig,
    }

    # Submit PoE
    resp = client.post("/poe/submit", json=poe_dict)
    assert resp.status_code == 200
    poe_result = resp.json()
    print(f"  PoE submitted: {poe_result.get('poe_id', 'unknown')}")
    print(f"  Verified: {poe_result.get('verified', False)}")
    print(f"  Payment: {poe_result.get('payment', 0)}")

    # Retrieve PoE
    resp = client.get(f"/job/{job_id}/poe")
    assert resp.status_code == 200
    stored_poe = resp.json()
    print(f"  PoE retrievable: YES")

    return True


def test_treasury_stats():
    """Test treasury stats after execution."""
    print("\n=== Test: Treasury Stats ===")

    from fastapi.testclient import TestClient
    client = TestClient(app)

    resp = client.get("/stats")
    assert resp.status_code == 200
    stats = resp.json()

    routing = stats.get("routing", {})
    treasury = stats.get("treasury", {})

    print(f"  Jobs completed: {routing.get('completed_jobs', 0)}")
    print(f"  Total transactions: {treasury.get('total_transactions', 0)}")
    print(f"  Total volume: {treasury.get('total_volume', 0)}")

    resp = client.get("/epoch/status")
    assert resp.status_code == 200
    epoch = resp.json()

    print(f"  Epoch: {epoch.get('epoch_id', 'unknown')}")
    print(f"  Gross revenue: {epoch.get('gross_revenue', '0')}")
    print(f"  Operators tracked: {epoch.get('operators_tracked', 0)}")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("SwarmView End-to-End Flow Test")
    print("=" * 60)

    # Setup
    os.environ["SWARMVISION_SIGNING_KEY"] = SIGNER_KEY
    reset_epoch_state()
    client_addr, operator_addr = setup_identities()

    # Run tests
    try:
        # Test 1: MRI Demo task
        pdf_bytes, analysis = test_mri_demo_task()

        # Test 2: Job submission
        job_id = test_job_submission()

        # Test 3: Agent execution
        proof, result_data = test_agent_execution(job_id)

        # Test 4: Result upload
        test_result_upload(job_id, result_data)

        # Test 5: PoE submission
        test_poe_submission(job_id, result_data)

        # Test 6: Treasury stats
        test_treasury_stats()

        # Save PDF for inspection
        output_dir = Path(__file__).parent.parent / "reports"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "test_mri_report.pdf"
        with open(output_path, "wb") as f:
            f.write(result_data)
        print(f"\n  Report saved: {output_path}")

        print("\n" + "=" * 60)
        print("END-TO-END SWARMVIEW FLOW PASSED")
        print("=" * 60)
        print(f"""
Summary:
  Client (Bee-1): {CLIENT_ENS}
  Operator (Bee-2): {OPERATOR_ENS}
  Task: swarmview.mri.demo
  Output: {output_path}
""")
        return 0

    except AssertionError as e:
        print(f"\n\nTEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
