"""Audio loading, resampling and (optional) semantic segmentation."""

from __future__ import annotations

from core.audio.loader import AudioInfo, AudioLoader
from core.audio.segmenter import SemanticSegmenter

__all__ = ["AudioInfo", "AudioLoader", "SemanticSegmenter"]
