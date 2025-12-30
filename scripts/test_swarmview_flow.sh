#!/bin/bash
#
# SwarmView End-to-End Flow Test
#
# Tests the complete execution path:
#   Bee-1 (SwarmView Client) → SwarmVision OS → Bee-2 (SwarmAgent) → PDF Report
#
# Usage:
#   ./scripts/test_swarmview_flow.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=================================================="
echo "SwarmView End-to-End Flow Test"
echo "=================================================="
echo ""

# Configuration
export SWARMVISION_URL="http://localhost:8000"
export SWARMVIEW_ENS="swarmview.swarmvision.eth"
export SWARMAGENT_ENS="rig1.swarmcompute.eth"

# Generate a test private key (deterministic for testing)
export SWARMVIEW_PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
export SWARMAGENT_PRIVATE_KEY="0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
export SWARMVISION_SIGNING_KEY="0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Cleaning up...${NC}"

    # Kill background processes
    if [ -n "$OS_PID" ]; then
        kill $OS_PID 2>/dev/null || true
    fi
    if [ -n "$AGENT_PID" ]; then
        kill $AGENT_PID 2>/dev/null || true
    fi

    # Remove temp files
    rm -rf "$PROJECT_DIR/reports" 2>/dev/null || true
    rm -f /tmp/swarmvision_os.log /tmp/swarmagent.log 2>/dev/null || true
}

trap cleanup EXIT

# ============================================================================
# STEP 1: Start SwarmVision OS
# ============================================================================

echo -e "${YELLOW}[1/5] Starting SwarmVision OS...${NC}"

python3 -c "
import sys
sys.path.insert(0, '.')
import uvicorn
from swarmvision.os.core import app

# Register test identities
from swarmvision.identity.ens import get_identity_service
from swarmvision.identity.crypto import private_key_to_address

ens = get_identity_service()

# Register client
client_addr = private_key_to_address('$SWARMVIEW_PRIVATE_KEY')
ens.register('swarmview.swarmvision.eth', client_addr, 'client')

# Register operator
operator_addr = private_key_to_address('$SWARMAGENT_PRIVATE_KEY')
ens.register('rig1.swarmcompute.eth', operator_addr, 'operator')

print(f'Registered client: swarmview.swarmvision.eth -> {client_addr}')
print(f'Registered operator: rig1.swarmcompute.eth -> {operator_addr}')

uvicorn.run(app, host='127.0.0.1', port=8000, log_level='warning')
" > /tmp/swarmvision_os.log 2>&1 &

OS_PID=$!
echo "  SwarmVision OS PID: $OS_PID"

# Wait for OS to be ready
echo "  Waiting for OS to start..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "  ${GREEN}SwarmVision OS is ready${NC}"
        break
    fi
    sleep 0.5
done

if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "  ${RED}Failed to start SwarmVision OS${NC}"
    cat /tmp/swarmvision_os.log
    exit 1
fi

# ============================================================================
# STEP 2: Start SwarmAgent (Bee-2)
# ============================================================================

echo ""
echo -e "${YELLOW}[2/5] Starting SwarmAgent (Bee-2)...${NC}"

python3 -c "
import sys
import asyncio
sys.path.insert(0, '.')
from swarmagent.daemon.agent import SwarmAgent, AgentConfig

config = AgentConfig(
    ens_name='rig1.swarmcompute.eth',
    private_key='$SWARMAGENT_PRIVATE_KEY',
    coordinator_url='http://localhost:8000',
    heartbeat_interval=5,
    job_poll_interval=2,
)

agent = SwarmAgent(config)
asyncio.run(agent.run())
" > /tmp/swarmagent.log 2>&1 &

AGENT_PID=$!
echo "  SwarmAgent PID: $AGENT_PID"

# Wait for agent to register
echo "  Waiting for agent to register..."
sleep 3

AGENTS=$(curl -s http://localhost:8000/agents | python3 -c "import sys,json; print(json.load(sys.stdin).get('total', 0))")
if [ "$AGENTS" -gt 0 ]; then
    echo -e "  ${GREEN}SwarmAgent registered${NC}"
else
    echo -e "  ${YELLOW}Agent may still be registering...${NC}"
fi

# ============================================================================
# STEP 3: Submit job via SwarmView CLI
# ============================================================================

echo ""
echo -e "${YELLOW}[3/5] Submitting job via SwarmView CLI...${NC}"

mkdir -p "$PROJECT_DIR/reports"

# Run SwarmView CLI
python3 swarmview/cli/main.py submit \
    --task swarmview.mri.demo \
    --input fixtures/sample_scan.json \
    --out reports/mri_report.pdf \
    --timeout 60 \
    --verify

SUBMIT_STATUS=$?

if [ $SUBMIT_STATUS -ne 0 ]; then
    echo -e "${RED}Job submission failed${NC}"
    echo "SwarmAgent log:"
    cat /tmp/swarmagent.log
    exit 1
fi

# ============================================================================
# STEP 4: Verify results
# ============================================================================

echo ""
echo -e "${YELLOW}[4/5] Verifying results...${NC}"

# Check PDF exists
if [ -f "$PROJECT_DIR/reports/mri_report.pdf" ]; then
    PDF_SIZE=$(stat -c%s "$PROJECT_DIR/reports/mri_report.pdf" 2>/dev/null || stat -f%z "$PROJECT_DIR/reports/mri_report.pdf" 2>/dev/null)
    echo -e "  ${GREEN}PDF created: reports/mri_report.pdf ($PDF_SIZE bytes)${NC}"
else
    echo -e "  ${RED}PDF not found${NC}"
    exit 1
fi

# Check PDF is valid (has PDF magic bytes)
if head -c 4 "$PROJECT_DIR/reports/mri_report.pdf" | grep -q '%PDF'; then
    echo -e "  ${GREEN}PDF format verified${NC}"
else
    echo -e "  ${RED}Invalid PDF format${NC}"
    exit 1
fi

# ============================================================================
# STEP 5: Check treasury stats
# ============================================================================

echo ""
echo -e "${YELLOW}[5/5] Checking treasury stats...${NC}"

STATS=$(curl -s http://localhost:8000/stats)
echo "$STATS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
routing = data.get('routing', {})
treasury = data.get('treasury', {})

print(f'  Jobs completed: {routing.get(\"completed_jobs\", 0)}')
print(f'  Total transactions: {treasury.get(\"total_transactions\", 0)}')
print(f'  Total volume: {treasury.get(\"total_volume\", 0)}')
"

# Check epoch status
EPOCH=$(curl -s http://localhost:8000/epoch/status)
echo "$EPOCH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Epoch: {data.get(\"epoch_id\", \"unknown\")}')
print(f'  Gross revenue: {data.get(\"gross_revenue\", \"0\")}')
print(f'  Operators tracked: {data.get(\"operators_tracked\", 0)}')
"

# ============================================================================
# SUCCESS
# ============================================================================

echo ""
echo "=================================================="
echo -e "${GREEN}END-TO-END SWARMVIEW FLOW PASSED${NC}"
echo "=================================================="
echo ""
echo "Summary:"
echo "  - Client (Bee-1): swarmview.swarmvision.eth"
echo "  - Operator (Bee-2): rig1.swarmcompute.eth"
echo "  - Task: swarmview.mri.demo"
echo "  - Output: reports/mri_report.pdf"
echo ""
