"""Tests for the recording status enum helpers."""

from __future__ import annotations

import unittest

from core.status import RecordingStatus, is_valid_status, status_values


class RecordingStatusTest(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(RecordingStatus.IMPORTED.value, "imported")
        self.assertEqual(RecordingStatus.ANALYZED.value, "analyzed")

    def test_string_enum_compares_to_value(self) -> None:
        self.assertEqual(RecordingStatus.TRANSCRIBED, "transcribed")
        self.assertIn(RecordingStatus.FAILED.value, status_values())

    def test_is_valid_status(self) -> None:
        self.assertTrue(is_valid_status(RecordingStatus.ANALYZING.value))
        self.assertFalse(is_valid_status("nope"))
        self.assertFalse(is_valid_status(""))


if __name__ == "__main__":
    unittest.main()
