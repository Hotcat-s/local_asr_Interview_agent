"""Facade that wires the individual core services into two independent stages.

``InterviewEngine`` is the only entry point the UI layer should touch.  The two
stages are strictly decoupled:

* :meth:`InterviewEngine.transcribe` runs audio -> VAD/ASR/punctuation/speaker
  (and optional semantic segmentation) and never touches the LLM.
* :meth:`InterviewEngine.analyze` runs batched LLM review over existing Q/A
  pairs and never touches the ASR models.

:meth:`InterviewEngine.run_full` keeps the old convenience pipeline for internal
or batch use; the GUI calls the two stages separately.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.asr.engine import FunASREngine
from core.audio.loader import AudioLoader
from core.audio.segmenter import SemanticSegmenter
from core.config import AnalysisConfig, AppConfig, LLMConfig
from core.diarization.qa_builder import QABuilder
from core.embeddings.bge import BGEEmbedder
from core.llm.analyzer import InterviewAnalyzer
from core.llm.client import LLMClient
from core.models.manager import ModelManager
from core.progress import (
    STAGE_DONE,
    STAGE_LLM,
    STAGE_LOAD,
    STAGE_QA,
    STAGE_SUMMARY,
    ProgressCallback,
    emit,
)
from core.schemas import InterviewReport, QAAnalysis, QAPair, Transcript

logger = logging.getLogger(__name__)


class InterviewEngine:
    """Orchestrate transcription, Q/A reconstruction and LLM review."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.load()
        self.model_manager = ModelManager()
        self.asr = FunASREngine(self.config.models, self.model_manager)
        self._audio_loader = AudioLoader()
        self._segmenter = SemanticSegmenter(
            embedder=BGEEmbedder(self.config.embedding_model),
            enabled=self.config.use_embedding_segmentation,
        )
        self._qa_builder = QABuilder()

    # ------------------------------------------------------ stage 1: transcription

    def transcribe(
        self,
        audio_path: str,
        progress: ProgressCallback | None = None,
        chunk_seconds: int | None = None,
    ) -> Transcript:
        """Run ASR only; this never invokes the LLM."""

        emit(progress, STAGE_LOAD, 0, 1, "读取音频…")
        info = self._audio_loader.prepare(audio_path)
        try:
            emit(
                progress,
                STAGE_LOAD,
                1,
                1,
                "音频就绪",
                f"时长 {info.duration:.0f} 秒",
            )
            limit = chunk_seconds if chunk_seconds is not None else self.config.chunk_seconds
            transcript = self.asr.transcribe(info.path, progress, chunk_seconds=limit)
            if self.config.use_embedding_segmentation:
                transcript.segments = self._segmenter.segment(transcript.segments, progress)
            if not transcript.duration and transcript.segments:
                transcript.duration = transcript.segments[-1].end
        finally:
            self._audio_loader.cleanup()
        emit(progress, STAGE_DONE, 1, 1, "音频转写完成", f"共 {len(transcript.segments)} 段")
        return transcript

    # ------------------------------------------------------------------ Q/A pairing

    def build_qa(
        self,
        transcript: Transcript,
        progress: ProgressCallback | None = None,
    ) -> list[QAPair]:
        emit(progress, STAGE_QA, 0, 1, "整理问答对…")
        pairs = self._qa_builder.build(transcript)
        emit(progress, STAGE_QA, 1, 1, "问答对整理完成", f"共 {len(pairs)} 组")
        logger.info("Reconstructed %d Q/A pairs", len(pairs))
        return pairs

    # ---------------------------------------------------------- stage 2: analysis

    def analyze(
        self,
        qa_pairs: list[QAPair],
        llm_config: LLMConfig | None = None,
        progress: ProgressCallback | None = None,
        analysis_config: AnalysisConfig | None = None,
    ) -> InterviewReport:
        """Run batched LLM analysis only; this never invokes the ASR models."""

        settings = analysis_config or self.config.analysis
        client = LLMClient(llm_config or self.config.llm)
        analyzer = InterviewAnalyzer(client, settings)

        if not qa_pairs:
            emit(progress, STAGE_SUMMARY, 0, 1, "没有可分析的问题")
            return analyzer.summarize([])

        batches = analyzer.plan_batches(qa_pairs)
        total_batches = len(batches)
        collected: dict[int, QAAnalysis] = {}

        for position, batch in enumerate(batches, start=1):
            first = batch[0].index + 1
            last = batch[-1].index + 1
            emit(
                progress,
                STAGE_LLM,
                position - 1,
                total_batches,
                f"分析第 {position}/{total_batches} 批…",
                f"第 {position}/{total_batches} 批（第 {first}-{last} 题）",
            )
            for analysis in analyzer.analyze_batch(batch):
                collected[analysis.index] = analysis
            emit(
                progress,
                STAGE_LLM,
                position,
                total_batches,
                f"已完成第 {position}/{total_batches} 批",
                f"第 {position}/{total_batches} 批（第 {first}-{last} 题）",
            )

        # Align strictly to the original question order; never drop a question.
        items: list[QAAnalysis] = []
        for pair in sorted(qa_pairs, key=lambda item: item.index):
            items.append(
                collected.get(pair.index)
                or analyzer.degraded_analysis(pair, "分析结果缺失")
            )

        if settings.enable_summary:
            emit(progress, STAGE_SUMMARY, 0, 1, "生成整体评价…")
            report = analyzer.summarize(items)
        else:
            report = _report_without_summary(items)

        emit(progress, STAGE_DONE, 1, 1, "复盘分析完成", f"共 {len(items)} 题")
        return report

    # ----------------------------------------------------------------------- pipeline

    def run_full(
        self,
        audio_path: str,
        llm_config: LLMConfig | None = None,
        progress: ProgressCallback | None = None,
    ) -> tuple[Transcript, list[QAPair], InterviewReport]:
        transcript = self.transcribe(audio_path, progress)
        qa_pairs = self.build_qa(transcript, progress)
        report = self.analyze(qa_pairs, llm_config, progress)
        return transcript, qa_pairs, report

    def unload(self) -> None:
        """Release the ASR models and their GPU memory."""

        self.asr.unload()


def _report_without_summary(items: list[QAAnalysis]) -> InterviewReport:
    created_at = datetime.now(timezone.utc).isoformat()
    if not items:
        return InterviewReport(
            overall_score=0.0, summary="", items=[], improvements=[], created_at=created_at
        )
    average = sum(item.score for item in items) / len(items)
    return InterviewReport(
        overall_score=round(average, 2),
        summary="",
        items=items,
        improvements=[],
        created_at=created_at,
    )


if __name__ == "__main__":  # pragma: no cover - manual smoke helper
    logging.basicConfig(level=logging.INFO)
    manager = ModelManager()
    logging.info("Local models: %s", manager.list_available())
