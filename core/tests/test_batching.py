"""Tests for batched analysis planning, JSON-array parsing and index alignment."""

from __future__ import annotations

import json
import unittest

from core.config import AnalysisConfig
from core.exceptions import LLMError
from core.llm.analyzer import InterviewAnalyzer
from core.llm.client import parse_json_array
from core.schemas import QAPair


def _qa(index: int, question: str = "q", answer: str = "a") -> QAPair:
    return QAPair(index, question, answer, "SPK0", "SPK1", float(index), float(index) + 1)


class PlanBatchesTest(unittest.TestCase):
    def test_groups_by_batch_size(self) -> None:
        analyzer = InterviewAnalyzer(None, AnalysisConfig(batch_size=3, max_chars_per_batch=10_000))
        pairs = [_qa(i) for i in range(7)]
        batches = analyzer.plan_batches(pairs)
        self.assertEqual([len(b) for b in batches], [3, 3, 1])
        self.assertEqual([p.index for b in batches for p in b], list(range(7)))

    def test_char_budget_splits_early(self) -> None:
        analyzer = InterviewAnalyzer(None, AnalysisConfig(batch_size=10, max_chars_per_batch=10))
        # each pair carries 10 chars (q+a); budget of 10 allows one per batch
        pairs = [_qa(i, question="1234", answer="567890") for i in range(3)]
        batches = analyzer.plan_batches(pairs)
        self.assertEqual([len(b) for b in batches], [1, 1, 1])

    def test_oversized_single_pair_occupies_own_batch(self) -> None:
        analyzer = InterviewAnalyzer(None, AnalysisConfig(batch_size=5, max_chars_per_batch=10))
        big = _qa(0, question="x" * 50, answer="y" * 50)
        small = _qa(1, question="q", answer="a")
        batches = analyzer.plan_batches([big, small])
        self.assertEqual([len(b) for b in batches], [1, 1])
        self.assertEqual(batches[0][0].index, 0)

    def test_preserves_order(self) -> None:
        analyzer = InterviewAnalyzer(None, AnalysisConfig(batch_size=2, max_chars_per_batch=10_000))
        pairs = [_qa(i) for i in range(5)]
        flat = [p.index for b in analyzer.plan_batches(pairs) for p in b]
        self.assertEqual(flat, [0, 1, 2, 3, 4])

    def test_empty(self) -> None:
        analyzer = InterviewAnalyzer(None, AnalysisConfig())
        self.assertEqual(analyzer.plan_batches([]), [])


class ParseJsonArrayTest(unittest.TestCase):
    def test_plain_array(self) -> None:
        self.assertEqual(parse_json_array('[{"index": 0}]'), [{"index": 0}])

    def test_fenced_array(self) -> None:
        raw = "结果如下：\n```json\n[{\"index\": 1, \"score\": 80}]\n```\n完成"
        self.assertEqual(parse_json_array(raw), [{"index": 1, "score": 80}])

    def test_wrapped_in_items(self) -> None:
        raw = '{"items": [{"index": 0}, {"index": 1}]}'
        self.assertEqual(parse_json_array(raw), [{"index": 0}, {"index": 1}])

    def test_trailing_prose_after_array(self) -> None:
        raw = '[{"index": 0}] 希望有帮助'
        self.assertEqual(parse_json_array(raw), [{"index": 0}])

    def test_trailing_comma(self) -> None:
        self.assertEqual(parse_json_array('[{"index": 0},]'), [{"index": 0}])

    def test_invalid_raises(self) -> None:
        with self.assertRaises(LLMError):
            parse_json_array("完全不是 json")
        with self.assertRaises(LLMError):
            parse_json_array("")


class _BatchClient:
    """Echoes an analysis entry per requested index, score = index + 10."""

    def __init__(self, *, omit: set[int] | None = None, scorable: bool = True) -> None:
        self.omit = omit or set()
        self.scorable = scorable
        self.calls = 0

    def chat_json_array(self, messages, **overrides):
        self.calls += 1
        payload = json.loads(messages[-1]["content"].split("：\n", 1)[1].split("\n\n")[0])
        result = []
        for item in payload:
            if item["index"] in self.omit:
                continue
            result.append(
                {
                    "index": item["index"],
                    "score": item["index"] + 10 if self.scorable else "bad",
                    "strengths": ["s"],
                    "weaknesses": ["w"],
                    "reference_answer": "ref",
                    "suggestion": "tip",
                }
            )
        return result


class _FailingArrayClient:
    def chat_json_array(self, messages, **overrides):
        raise LLMError("boom")


class AnalyzeBatchTest(unittest.TestCase):
    def test_analyze_batch_aligns_by_index(self) -> None:
        batch = [_qa(0), _qa(1), _qa(2)]
        analyzer = InterviewAnalyzer(_BatchClient())
        results = analyzer.analyze_batch(batch)
        self.assertEqual([r.index for r in results], [0, 1, 2])
        self.assertEqual([r.score for r in results], [10.0, 11.0, 12.0])
        self.assertEqual(results[0].reference_answer, "ref")

    def test_missing_entry_degrades_without_dropping(self) -> None:
        batch = [_qa(0), _qa(1), _qa(2)]
        analyzer = InterviewAnalyzer(_BatchClient(omit={1}))
        results = analyzer.analyze_batch(batch)
        self.assertEqual([r.index for r in results], [0, 1, 2])
        # index 1 missing AND positional fallback shifts -> still present, degraded
        self.assertTrue(len(results) == 3)

    def test_failing_client_degrades_every_pair(self) -> None:
        batch = [_qa(0), _qa(1)]
        results = InterviewAnalyzer(_FailingArrayClient()).analyze_batch(batch)
        self.assertEqual([r.index for r in results], [0, 1])
        self.assertTrue(all(r.score == 0.0 for r in results))
        self.assertTrue(all(r.weaknesses for r in results))

    def test_single_call_per_batch(self) -> None:
        client = _BatchClient()
        InterviewAnalyzer(client).analyze_batch([_qa(0), _qa(1)])
        self.assertEqual(client.calls, 1)

    def test_bad_score_falls_back_to_zero(self) -> None:
        analyzer = InterviewAnalyzer(_BatchClient(scorable=False))
        results = analyzer.analyze_batch([_qa(0)])
        self.assertEqual(results[0].score, 0.0)


class _EngineClient:
    """Returns aligned entries for every requested index."""

    def chat_json_array(self, messages, **overrides):
        payload = json.loads(messages[-1]["content"].split("：\n", 1)[1].split("\n\n")[0])
        return [
            {
                "index": item["index"],
                "score": 50,
                "strengths": [],
                "weaknesses": [],
                "reference_answer": "",
                "suggestion": "",
            }
            for item in payload
        ]

    def chat_json(self, messages, **overrides):
        return {"overall_score": 66, "summary": "ok", "improvements": ["x"]}


class EngineAnalysisTest(unittest.TestCase):
    """`InterviewEngine.analyze` must return every question in index order."""

    def _analyze(self, pairs, *, enable_summary=True, batch_size=2):
        from unittest import mock

        from core.config import AnalysisConfig, AppConfig
        from core.engine import InterviewEngine

        config = AppConfig(analysis=AnalysisConfig(batch_size=batch_size, enable_summary=enable_summary))
        engine = InterviewEngine(config)
        events = []
        with mock.patch("core.engine.LLMClient", return_value=_EngineClient()):
            report = engine.analyze(pairs, progress=events.append)
        return report, events

    def test_all_indices_present_in_order(self) -> None:
        pairs = [_qa(2), _qa(0), _qa(1)]  # deliberately unsorted input
        report, _ = self._analyze(pairs)
        self.assertEqual([item.index for item in report.items], [0, 1, 2])
        self.assertEqual(report.overall_score, 66.0)

    def test_progress_reports_batches_and_summary(self) -> None:
        report, events = self._analyze([_qa(i) for i in range(4)], batch_size=2)
        from core.progress import STAGE_LLM, STAGE_SUMMARY

        llm_events = [e for e in events if e.stage == STAGE_LLM]
        summary_events = [e for e in events if e.stage == STAGE_SUMMARY]
        self.assertEqual(len(llm_events), 4)  # 2 batches x (start + done)
        self.assertEqual(llm_events[-1].current, 2)
        self.assertEqual(llm_events[-1].total, 2)
        self.assertTrue(summary_events)
        self.assertEqual(len(report.items), 4)

    def test_summary_can_be_disabled(self) -> None:
        report, _ = self._analyze([_qa(0), _qa(1)], enable_summary=False)
        self.assertEqual(report.summary, "")
        self.assertEqual(len(report.items), 2)

    def test_empty_pairs(self) -> None:
        report, _ = self._analyze([])
        self.assertEqual(report.items, [])


if __name__ == "__main__":
    unittest.main()
