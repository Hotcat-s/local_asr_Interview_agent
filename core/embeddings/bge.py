"""Lazy wrapper around ``sentence-transformers`` for BGE embeddings.

The dependency is optional: when ``sentence-transformers`` is not installed or
the model cannot be loaded, :meth:`BGEEmbedder.is_available` returns ``False``
and callers fall back to the native FunASR segmentation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class BGEEmbedder:
    """Encode Chinese text into sentence embeddings.

    The heavy import and model load happen inside :meth:`load`, so importing
    this module is cheap and safe even without the optional dependency.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        self.model_name = model_name
        self._model = None

    @staticmethod
    def is_available() -> bool:
        """Return ``True`` when ``sentence-transformers`` can be imported."""

        try:
            import sentence_transformers  # noqa: F401,PLC0415
        except ImportError:
            return False
        return True

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> bool:
        """Load the model; returns ``False`` when unavailable."""

        if self._model is not None:
            return True
        if not self.is_available():
            logger.warning(
                "sentence-transformers not installed; semantic segmentation disabled"
            )
            return False
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            self._model = SentenceTransformer(self.model_name)
            logger.info("Loaded embedding model %s", self.model_name)
            return True
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.warning("Failed to load embedding model %s: %s", self.model_name, exc)
            self._model = None
            return False

    def encode(self, texts: list[str]):
        """Return an ``(n, dim)`` numpy array of L2-normalised embeddings."""

        if not texts:
            import numpy as np  # noqa: PLC0415

            return np.zeros((0, 0), dtype="float32")
        if self._model is None and not self.load():
            raise RuntimeError("BGEEmbedder is not available")
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors

    def unload(self) -> None:
        self._model = None
