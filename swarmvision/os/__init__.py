"""
SwarmVision OS — Coordination Layer

The OS provides:
- Job intake and routing
- Agent registration
- Proof verification
- Treasury accounting
"""

from .core import app, main

__all__ = ["app", "main"]
