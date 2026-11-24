"""Tests for the v5 font configuration fields (``font_family`` / ``font_size``)."""

from __future__ import annotations

import unittest

from core.config import AppConfig


class FontConfigDefaultTest(unittest.TestCase):
    def test_default_values(self) -> None:
        config = AppConfig.default()
        self.assertEqual(config.font_family, "")
        self.assertEqual(config.font_size, 12)

    def test_constructor_defaults(self) -> None:
        config = AppConfig()
        self.assertEqual(config.font_family, "")
        self.assertEqual(config.font_size, 12)


class FontConfigRoundTripTest(unittest.TestCase):
    def test_round_trip_custom_values(self) -> None:
        config = AppConfig(font_family="Microsoft YaHei", font_size=20)
        restored = AppConfig.from_dict(config.to_dict())
        self.assertEqual(restored.font_family, "Microsoft YaHei")
        self.assertEqual(restored.font_size, 20)

    def test_to_dict_includes_font_fields(self) -> None:
        data = AppConfig.default().to_dict()
        self.assertIn("font_family", data)
        self.assertIn("font_size", data)
        self.assertEqual(data["font_family"], "")
        self.assertEqual(data["font_size"], 12)


class FontSizeRobustnessTest(unittest.TestCase):
    def _size(self, value: object) -> int:
        return AppConfig.from_dict({"llm": {}, "models": {}, "font_size": value}).font_size

    def test_non_numeric_falls_back_to_default(self) -> None:
        self.assertEqual(self._size("abc"), 12)
        self.assertEqual(self._size(None), 12)

    def test_negative_is_clamped_to_min(self) -> None:
        self.assertEqual(self._size(-5), 9)

    def test_zero_is_clamped_to_min(self) -> None:
        self.assertEqual(self._size(0), 9)

    def test_oversized_is_clamped_to_max(self) -> None:
        self.assertEqual(self._size(999), 24)

    def test_in_range_value_is_preserved(self) -> None:
        self.assertEqual(self._size(18), 18)

    def test_boundaries_are_preserved(self) -> None:
        self.assertEqual(self._size(9), 9)
        self.assertEqual(self._size(24), 24)

    def test_invalid_values_do_not_raise(self) -> None:
        for value in ("abc", None, -5, 0, 999, [], {}, True):
            with self.subTest(value=value):
                self.assertIsInstance(self._size(value), int)


class FontFamilyRobustnessTest(unittest.TestCase):
    def _family(self, value: object) -> str:
        return AppConfig.from_dict({"llm": {}, "models": {}, "font_family": value}).font_family

    def test_none_falls_back_to_empty(self) -> None:
        self.assertEqual(self._family(None), "")

    def test_number_falls_back_to_empty(self) -> None:
        self.assertEqual(self._family(123), "")

    def test_non_string_falls_back_to_empty(self) -> None:
        self.assertEqual(self._family(["Arial"]), "")

    def test_valid_string_is_preserved(self) -> None:
        self.assertEqual(self._family("Consolas"), "Consolas")

    def test_invalid_values_do_not_raise(self) -> None:
        for value in (None, 123, ["Arial"], {"a": 1}):
            with self.subTest(value=value):
                self.assertIsInstance(self._family(value), str)


class FontConfigBackwardCompatibilityTest(unittest.TestCase):
    def test_old_config_without_font_fields(self) -> None:
        old = {
            "models": {"device": "cuda"},
            "llm": {"model": "gpt-4o-mini"},
            "analysis": {"batch_size": 3},
            "data_dir": "data",
            "chunk_seconds": 300,
            "theme": "dark",
        }
        restored = AppConfig.from_dict(old)
        self.assertEqual(restored.font_family, "")
        self.assertEqual(restored.font_size, 12)


if __name__ == "__main__":
    unittest.main()
