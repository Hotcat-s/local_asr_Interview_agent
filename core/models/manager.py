"""Resolve and validate the locally downloaded FunASR models."""

from __future__ import annotations

import logging
from pathlib import Path

from core.exceptions import ModelNotFoundError
from core.models.registry import MODEL_KEYS, MODEL_REGISTRY, MODELS_ROOT_RELPATH

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


class ModelManager:
    """Locate model directories without performing any network access.

    The models are expected to be present under ``<repo>/core/models`` (the
    default).  Passing ``models_root`` allows tests or alternative deployments
    to point elsewhere.
    """

    def __init__(self, models_root: str | None = None) -> None:
        if models_root:
            self.models_root = Path(models_root).expanduser().resolve()
        else:
            self.models_root = (_REPO_ROOT / MODELS_ROOT_RELPATH).resolve()

    def path_for(self, key: str) -> Path:
        if key not in MODEL_REGISTRY:
            raise KeyError(f"Unknown model key: {key!r}; expected one of {MODEL_KEYS}")
        return self.models_root / MODEL_REGISTRY[key].relative_path

    def resolve(self, key: str) -> str:
        """Return the absolute path for ``key``, raising if it is missing."""

        path = self.path_for(key)
        if not path.exists():
            raise ModelNotFoundError(f"Model {key!r} not found at {path}")
        return str(path)

    def exists(self, key: str) -> bool:
        return self.path_for(key).exists()

    def list_available(self) -> list[dict]:
        result: list[dict] = []
        for key in MODEL_KEYS:
            entry = MODEL_REGISTRY[key]
            path = self.path_for(key)
            result.append(
                {
                    "key": key,
                    "name": entry.name,
                    "path": str(path),
                    "exists": path.exists(),
                }
            )
        return result

    def all_paths(self) -> dict[str, str]:
        """Return resolved paths for every key, tolerating missing models.

        Missing entries fall back to the (non-existent) expected path so callers
        such as the engine builder can surface a clear error later.
        """

        return {key: str(self.path_for(key)) for key in MODEL_KEYS}
