"""Tests for robust JSON parsing and analyzer degradation."""

from __future__ import annotations

import unittest

from core.exceptions import LLMError
from core.llm.analyzer import InterviewAnalyzer
from core.llm.client import parse_json_response
from core.schemas import QAPair


class ParseJsonResponseTest(unittest.TestCase):
    def test_plain_object(self) -> None:
        self.assertEqual(parse_json_response('{"score": 80}'), {"score": 80})

    def test_fenced_json(self) -> None:
        raw = "这是结果：\n```json\n{\"score\": 70, \"s\": [\"a\"]}\n```\n完成"
        self.assertEqual(parse_json_response(raw), {"score": 70, "s": ["a"]})

    def test_prose_wrapped(self) -> None:
        raw = '好的，结果如下 {"score": 60} 希望有帮助'
        self.assertEqual(parse_json_response(raw), {"score": 60})

    def test_trailing_comma(self) -> None:
        self.assertEqual(parse_json_response('{"score": 50,}'), {"score": 50})

    def test_top_level_array_is_wrapped(self) -> None:
        self.assertEqual(parse_json_response("```json\n[1, 2]\n```"), {"items": [1, 2]})

    def test_invalid_raises(self) -> None:
        with self.assertRaises(LLMError):
            parse_json_response("完全不是 json")
        with self.assertRaises(LLMError):
            parse_json_response("")


class _FailingClient:
    def chat_json(self, messages, **overrides):
        raise LLMError("boom")


class _StubClient:
    def chat_json(self, messages, **overrides):
        return {
            "score": 120,  # clamped to 100
            "strengths": "能做",
            "weaknesses": ["不懂原理"],
            "reference_answer": "标准答案",
            "suggestion": "多看书",
        }


class AnalyzerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.qa = QAPair(0, "问题", "回答", "SPK0", "SPK1", 0.0, 1.0)

    def test_analyze_qa_success_and_score_clamp(self) -> None:
        result = InterviewAnalyzer(_StubClient()).analyze_qa(self.qa)
        self.assertEqual(result.score, 100.0)
        self.assertEqual(result.strengths, ["能做"])
        self.assertEqual(result.reference_answer, "标准答案")

    def test_analyze_qa_degrades_on_failure(self) -> None:
        result = InterviewAnalyzer(_FailingClient()).analyze_qa(self.qa)
        self.assertEqual(result.score, 0.0)
        self.assertTrue(result.weaknesses)
        self.assertEqual(result.index, 0)

    def test_summarize_fallback_uses_average(self) -> None:
        analyzer = InterviewAnalyzer(_FailingClient())
        items = [analyzer.analyze_qa(self.qa), analyzer.analyze_qa(self.qa)]
        report = analyzer.summarize(items)
        self.assertEqual(report.overall_score, 0.0)
        self.assertEqual(len(report.items), 2)

    def test_summarize_empty(self) -> None:
        report = InterviewAnalyzer(_FailingClient()).summarize([])
        self.assertEqual(report.overall_score, 0.0)
        self.assertEqual(report.items, [])


if __name__ == "__main__":
    unittest.main()
