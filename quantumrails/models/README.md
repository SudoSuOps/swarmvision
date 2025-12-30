# QuantumRails Models

Model definitions for SwarmVision distributed compute.

## Structure

```
models/
├── README.md
├── registry.json       # Model registry
└── definitions/        # Model configs
    ├── llm/
    ├── vision/
    └── audio/
```

## Model Registry

Models are registered with:
- `model_id` — Unique identifier
- `type` — llm, vision, audio, etc.
- `requirements` — GPU, VRAM, etc.
- `source` — HuggingFace, local, etc.

## Example

```json
{
  "model_id": "swarmhealth-diabetes-v3",
  "type": "llm",
  "source": "huggingface",
  "repo": "Trustcat/swarmhealth-diabetes-companion",
  "requirements": {
    "min_vram_gb": 16,
    "min_gpu_count": 1
  }
}
```

## Adding Models

1. Create definition in `definitions/`
2. Register in `registry.json`
3. Test locally with SwarmAgent
4. Submit PR
