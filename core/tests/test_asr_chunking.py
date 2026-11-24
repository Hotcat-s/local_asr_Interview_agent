"""Pure-data tests for cross-chunk speaker label alignment."""

from __future__ import annotations

import unittest

from core.asr.engine import _SpeakerAligner


class SpeakerAlignerTest(unittest.TestCase):
    def test_first_chunk_assigns_by_appearance(self) -> None:
        aligner = _SpeakerAligner()
        mapping = aligner.align(["SPK0", "SPK1"], first_chunk=True)
        self.assertEqual(mapping, {"SPK0": "SPK0", "SPK1": "SPK1"})

    def test_continuation_keeps_speaker_identity(self) -> None:
        aligner = _SpeakerAligner()
        aligner.align(["SPK0", "SPK1"], first_chunk=True)  # ends with SPK1
        # next chunk starts with whoever continued (local 0) then the other
        mapping = aligner.align(["SPK0", "SPK1"], first_chunk=False)
        # first local continues SPK1; the other maps back to SPK0
        self.assertEqual(mapping, {"SPK0": "SPK1", "SPK1": "SPK0"})

    def test_new_speaker_gets_appended(self) -> None:
        aligner = _SpeakerAligner()
        aligner.align(["SPK0", "SPK1"], first_chunk=True)
        mapping = aligner.align(["SPK0", "SPK2", "SPK1"], first_chunk=False)
        self.assertEqual(mapping["SPK0"], "SPK1")  # continuation
        self.assertIn("SPK2", mapping.values())
        self.assertEqual(len(set(mapping.values())), 3)

    def test_empty_chunk_is_safe(self) -> None:
        aligner = _SpeakerAligner()
        self.assertEqual(aligner.align([], first_chunk=True), {})


class ParseSegmentsOffsetTest(unittest.TestCase):
    """Timestamps are per-chunk; the engine adds the offset (verify the math)."""

    def test_parse_then_offset(self) -> None:
        from core.asr.engine import FunASREngine

        result = {"text": "hi", "sentence_info": [{"text": "hi", "start": 0, "end": 1000, "spk": 0}]}
        segments = FunASREngine._parse_segments(result)
        offset = 300.0
        shifted = [(s.start + offset, s.end + offset) for s in segments]
        self.assertEqual(shifted, [(300.0, 301.0)])


if __name__ == "__main__":
    unittest.main()
