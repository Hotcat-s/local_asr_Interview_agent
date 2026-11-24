"""Per-question analysis and overall interview summarisation.

Analysis is *batched*: several Q/A pairs are sent in a single LLM request so the
model keeps surrounding context, while the batch size and character budget stop
prompts from growing without bound.  See :meth:`InterviewAnalyzer.plan_batches`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from core.config import AnalysisConfig
from core.exceptions import LLMError
from core.llm.client import LLMClient
from core.llm.prompts import BATCH_ANALYSIS_PROMPT, QA_ANALYSIS_PROMPT, SUMMARY_PROMPT, SYSTEM_PROMPT
from core.schemas import InterviewReport, QAAnalysis, QAPair

logger = logging.getLogger(__name__)


class InterviewAnalyzer:
    """Turn reconstructed Q/A pairs into an :class:`InterviewReport`."""

    def __init__(
        self,
        client: LLMClient,
        analysis_config: AnalysisConfig | None = None,
    ) -> None:
        self.client = client
        self.config = analysis_config or AnalysisConfig()

    # ----------------------------------------------------------------- batches

    def plan_batches(self, qa_pairs: list[QAPair]) -> list[list[QAPair]]:
        """Group ``qa_pairs`` into analysis batches.

        A batch holds at most ``config.batch_size`` pairs and at most
        ``config.max_chars_per_batch`` characters (counting question + answer).
        A single oversized pair occupies its own batch.  Original order is kept.
        """

        batch_size = max(1, int(self.config.batch_size))
        max_chars = max(1, int(self.config.max_chars_per_batch))

        batches: list[list[QAPair]] = []
        current: list[QAPair] = []
        current_chars = 0

        for pair in qa_pairs:
            size = len(pair.question) + len(pair.answer)
            if current and (len(current) >= batch_size or current_chars + size > max_chars):
                batches.append(current)
                current = []
                current_chars = 0
            current.append(pair)
            current_chars += size
        if current:
            batches.append(current)
        return batches

    # ----------------------------------------------------------------- analysis

    def analyze_batch(self, batch: list[QAPair]) -> list[QAAnalysis]:
        """Analyse a whole batch with one LLM call.

        Results are returned in the same order as ``batch``.  Missing or
        unparsable entries degrade to a zero-score analysis instead of raising.
        """

        if not batch:
            return []

        payload = [
            {"index": pair.index, "question": pair.question, "answer": pair.answer}
            for pair in batch
        ]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": BATCH_ANALYSIS_PROMPT.format(
                    count=len(batch),
                    items=json.dumps(payload, ensure_ascii=False),
                ),
            },
        ]
        try:
            entries = self.client.chat_json_array(messages)
        except LLMError as exc:
            logger.warning("Batch analysis failed: %s", exc)
            return [self.degraded_analysis(pair, f"分析失败: {exc}") for pair in batch]

        by_index: dict[int, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            idx = _coerce_index(entry.get("index"))
            if idx is None or idx in by_index:
                continue
            by_index[idx] = entry

        positional_ok = len(entries) == len(batch)
        results: list[QAAnalysis] = []
        for position, pair in enumerate(batch):
            entry = by_index.get(pair.index)
            if entry is None and positional_ok and isinstance(entries[position], dict):
                entry = entries[position]
            if entry is None:
                results.append(self.degraded_analysis(pair, "LLM 未返回该题结果"))
            else:
                results.append(self._from_entry(pair, entry))
        return results

    def analyze_qa(self, qa: QAPair) -> QAAnalysis:
        """Analyse a single Q/A pair (used when ``batch_size == 1``)."""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": QA_ANALYSIS_PROMPT.format(question=qa.question, answer=qa.answer),
            },
        ]
        try:
            data = self.client.chat_json(messages)
        except LLMError as exc:
            logger.warning("Q/A %s analysis failed: %s", qa.index, exc)
            return self.degraded_analysis(qa, f"分析失败: {exc}")
        return self._from_entry(qa, data)

    def degraded_analysis(self, qa: QAPair, reason: str) -> QAAnalysis:
        """Return a zero-score placeholder so a failure never drops a question."""

        return QAAnalysis(
            index=qa.index,
            question=qa.question,
            answer=qa.answer,
            score=0.0,
            strengths=[],
            weaknesses=[reason],
            reference_answer="",
            suggestion="",
        )

    def summarize(self, items: list[QAAnalysis]) -> InterviewReport:
        created_at = datetime.now(timezone.utc).isoformat()
        if not items:
            return InterviewReport(
                overall_score=0.0,
                summary="没有可分析的问题回答。",
                items=[],
                improvements=[],
                created_at=created_at,
            )

        payload = json.dumps(
            [
                {
                    "index": item.index,
                    "score": item.score,
                    "strengths": item.strengths,
                    "weaknesses": item.weaknesses,
                }
                for item in items
            ],
            ensure_ascii=False,
        )
        avg_score = sum(item.score for item in items) / len(items)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": SUMMARY_PROMPT.format(items=payload)},
        ]
        try:
            data = self.client.chat_json(messages)
        except LLMError as exc:
            logger.warning("Overall summary failed: %s", exc)
            return InterviewReport(
                overall_score=round(avg_score, 2),
                summary=f"整体总结生成失败：{exc}。以下为逐题平均分。",
                items=items,
                improvements=[],
                created_at=created_at,
            )

        return InterviewReport(
            overall_score=_coerce_score(data.get("overall_score"), fallback=avg_score),
            summary=str(data.get("summary", "") or ""),
            items=items,
            improvements=_coerce_str_list(data.get("improvements")),
            created_at=created_at,
        )

    # ------------------------------------------------------------------ helpers

    def _from_entry(self, qa: QAPair, data: dict) -> QAAnalysis:
        return QAAnalysis(
            index=qa.index,
            question=qa.question,
            answer=qa.answer,
            score=_coerce_score(data.get("score")),
            strengths=_coerce_str_list(data.get("strengths")),
            weaknesses=_coerce_str_list(data.get("weaknesses")),
            reference_answer=str(data.get("reference_answer", "") or ""),
            suggestion=str(data.get("suggestion", "") or ""),
        )


def _coerce_index(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _coerce_score(value: object, fallback: float = 0.0) -> float:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(100.0, score))


def _coerce_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
