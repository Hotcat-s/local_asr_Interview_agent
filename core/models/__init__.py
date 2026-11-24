"""Package for local model discovery and resolution."""

from __future__ import annotations

from core.models.manager import ModelManager
from core.models.registry import MODEL_REGISTRY, ModelEntry

__all__ = ["MODEL_REGISTRY", "ModelEntry", "ModelManager"]
