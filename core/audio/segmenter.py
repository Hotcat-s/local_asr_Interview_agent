"""Semantic segmentation on top of native FunASR sentence output.

FunASR already splits speech into speaker-attributed sentences.  When BGE
embeddings are enabled, adjacent same-speaker sentences whose embeddings are
semantically close are merged into a single block, which yields more coherent
question / answer units.  When embeddings are unavailable the original
segments are returned unchanged.
"""

from __future__ import annotations

import logging

from core.embeddings.bge import BGEEmbedder
from core.progress import STAGE_SEGMENT, ProgressCallback, emit
from core.schemas import TranscriptSegment

logger = logging.getLogger(__name__)


class SemanticSegmenter:
    """Merge same-speaker neighbouring sentences using embedding similarity."""

    def __init__(
        self,
        embedder: BGEEmbedder | None = None,
        enabled: bool = False,
        similarity_threshold: float = 0.6,
    ) -> None:
        self.embedder = embedder
        self.enabled = enabled
        self.similarity_threshold = similarity_threshold

    def segment(
        self,
        segments: list[TranscriptSegment],
        progress: ProgressCallback | None = None,
    ) -> list[TranscriptSegment]:
        if not segments:
            return []
        if not self.enabled or self.embedder is None:
            return list(segments)

        emit(progress, STAGE_SEGMENT, 0, 1, "语义分段中…")
        texts = [seg.text for seg in segments]
        try:
            vectors = self.embedder.encode(texts)
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.warning("Embedding segmentation failed, using native segments: %s", exc)
            return list(segments)

        merged: list[TranscriptSegment] = [segments[0]]
        for i in range(1, len(segments)):
            prev = segments[i - 1]
            cur = segments[i]
            same_speaker = prev.speaker == cur.speaker
            similar = float(vectors[i] @ vectors[i - 1]) >= self.similarity_threshold
            if same_speaker and similar:
                last = merged[-1]
                merged[-1] = TranscriptSegment(
                    start=last.start,
                    end=cur.end,
                    text=f"{last.text} {cur.text}".strip(),
                    speaker=last.speaker,
                )
            else:
                merged.append(cur)

        emit(progress, STAGE_SEGMENT, 1, 1, "语义分段完成")
        return merged
