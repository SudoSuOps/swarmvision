# QuantumRails Artifacts

Build outputs and cached results.

## Purpose

Artifacts store:
- Compiled models (ONNX, TensorRT)
- Cached weights
- Intermediate results
- Proof archives

## Structure

```
artifacts/
├── README.md
├── models/           # Compiled model files
├── cache/            # Temporary cache
└── proofs/           # Archived proofs
```

## Artifact Types

| Type | Extension | Description |
|------|-----------|-------------|
| ONNX | `.onnx` | Cross-platform model |
| TensorRT | `.engine` | NVIDIA optimized |
| Safetensors | `.safetensors` | HuggingFace format |
| Proof | `.json` | Execution proof |

## Storage

Artifacts are local to each SwarmAgent.

Future: Distributed artifact cache via IPFS or similar.

## Cleanup

```bash
# Clear cache older than 7 days
find artifacts/cache -mtime +7 -delete

# Archive old proofs
tar -czf proofs-$(date +%Y%m).tar.gz artifacts/proofs/
```
