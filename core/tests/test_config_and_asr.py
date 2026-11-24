"""Tests for config persistence, model path resolution and ASR parsing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.asr.engine import FunASREngine
from core.config import AnalysisConfig, AppConfig, LLMConfig, ModelConfig
from core.exceptions import ModelNotFoundError
from core.models.manager import ModelManager


class ConfigTest(unittest.TestCase):
    def test_default_and_round_trip(self) -> None:
        config = AppConfig.default()
        config.llm.model = "my-local-model"
        config.models.device = "cpu"
        data = config.to_dict()
        restored = AppConfig.from_dict(data)
        self.assertEqual(restored.llm.model, "my-local-model")
        self.assertEqual(restored.models.device, "cpu")

    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "config.json"
            config = AppConfig(models=ModelConfig(device="cpu"), llm=LLMConfig(api_key="k"))
            config.save(str(path))
            self.assertTrue(path.exists())
            loaded = AppConfig.load(str(path))
            self.assertEqual(loaded.llm.api_key, "k")
            self.assertEqual(loaded.models.device, "cpu")

    def test_load_missing_returns_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            loaded = AppConfig.load(str(Path(tmp) / "nope.json"))
            self.assertEqual(loaded.llm.provider, "openai")

    def test_load_corrupt_returns_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(AppConfig.load(str(path)).llm.provider, "openai")

    def test_from_dict_ignores_unknown_keys(self) -> None:
        restored = AppConfig.from_dict({"llm": {"model": "m", "unknown": 1}, "bogus": 2})
        self.assertEqual(restored.llm.model, "m")

    def test_v1_config_upgrades_with_defaults(self) -> None:
        v1 = {
            "models": {"device": "cuda"},
            "llm": {"model": "gpt-4o-mini"},
            "data_dir": "data",
            "use_embedding_segmentation": False,
            "embedding_model": "BAAI/bge-small-zh-v1.5",
            "db_path": "data/interview.db",
            "config_path": "config.json",
        }
        restored = AppConfig.from_dict(v1)
        self.assertEqual(restored.analysis.batch_size, 3)
        self.assertEqual(restored.chunk_seconds, 300)
        self.assertEqual(restored.theme, "dark")

    def test_analysis_round_trip(self) -> None:
        config = AppConfig(analysis=AnalysisConfig(batch_size=5, max_chars_per_batch=4000))
        restored = AppConfig.from_dict(config.to_dict())
        self.assertEqual(restored.analysis.batch_size, 5)
        self.assertEqual(restored.analysis.max_chars_per_batch, 4000)


class ModelManagerTest(unittest.TestCase):
    def test_default_models_root_is_repo_core_models(self) -> None:
        manager = ModelManager()
        self.assertTrue(str(manager.models_root).endswith("core/models"))

    def test_all_paths_has_four_keys(self) -> None:
        paths = ModelManager().all_paths()
        self.assertEqual(set(paths), {"asr", "vad", "punc", "spk"})

    def test_missing_model_raises(self) -> None:
        manager = ModelManager(models_root="/nonexistent/models")
        with self.assertRaises(ModelNotFoundError):
            manager.resolve("asr")

    def test_list_available_shape(self) -> None:
        entries = ModelManager().list_available()
        self.assertEqual(len(entries), 4)
        self.assertIn("exists", entries[0])
        self.assertIn("name", entries[0])


class FunASRParseTest(unittest.TestCase):
    def test_parse_sentence_info_ms_to_seconds(self) -> None:
        result = {
            "text": "你好你好呀",
            "sentence_info": [
                {"text": "你好", "start": 0, "end": 1000, "spk": 0},
                {"text": "你好呀", "start": 1000, "end": 2500, "spk": 1},
            ],
        }
        segments = FunASREngine._parse_segments(result)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].speaker, "SPK0")
        self.assertAlmostEqual(segments[0].end, 1.0)
        self.assertEqual(segments[1].speaker, "SPK1")
        self.assertAlmostEqual(segments[1].start, 1.0)

    def test_parse_sentence_key_alias(self) -> None:
        result = {"text": "x", "sentence_info": [{"sentence": "句子", "start": 0, "end": 500, "spk": 2}]}
        segments = FunASREngine._parse_segments(result)
        self.assertEqual(segments[0].text, "句子")
        self.assertEqual(segments[0].speaker, "SPK2")

    def test_fallback_to_single_segment(self) -> None:
        result = {"text": "整段文本", "timestamp": [[0, 1000], [1000, 2000]]}
        segments = FunASREngine._parse_segments(result)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].text, "整段文本")
        self.assertAlmostEqual(segments[0].end, 2.0)


if __name__ == "__main__":
    unittest.main()
