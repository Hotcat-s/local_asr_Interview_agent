"""Application configuration models and JSON persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Supported range for the main content area font size (points).
_MIN_FONT_SIZE = 9
_MAX_FONT_SIZE = 24
_DEFAULT_FONT_SIZE = 12


@dataclass
class ModelConfig:
    """Paths to the local FunASR models.

    Empty strings mean "resolve through :class:`core.models.manager.ModelManager`".
    """

    asr: str = ""
    vad: str = ""
    punc: str = ""
    spk: str = ""
    device: str = "cuda"


@dataclass
class LLMConfig:
    """OpenAI-compatible LLM settings (used for both cloud and local servers)."""

    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout: float = 120.0


@dataclass
class AnalysisConfig:
    """Batched LLM analysis parameters.

    ``batch_size`` Q/A pairs are sent per request, but a batch is cut early
    whenever the combined character count would exceed ``max_chars_per_batch``.
    """

    batch_size: int = 3
    max_chars_per_batch: int = 8000
    concurrency: int = 1
    enable_summary: bool = True


@dataclass
class AppConfig:
    """Top level application configuration."""

    models: ModelConfig = field(default_factory=ModelConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    data_dir: str = "data"
    use_embedding_segmentation: bool = False
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    db_path: str = "data/interview.db"
    config_path: str = "config.json"
    chunk_seconds: int = 300
    theme: str = "dark"
    font_family: str = ""
    font_size: int = 12

    @classmethod
    def default(cls) -> "AppConfig":
        return cls()

    @classmethod
    def load(cls, path: str | None = None) -> "AppConfig":
        """Load configuration from ``path``; return defaults if not present."""

        config_path = Path(path) if path else _REPO_ROOT / "config.json"
        if not config_path.exists():
            logger.info("Config file %s not found, using defaults", config_path)
            return cls.default()
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read config %s: %s, using defaults", config_path, exc)
            return cls.default()
        if not isinstance(data, dict):
            logger.warning("Config %s is not a JSON object, using defaults", config_path)
            return cls.default()
        config = cls.from_dict(data)
        config.config_path = str(config_path)
        return config

    def save(self, path: str | None = None) -> None:
        """Persist configuration as JSON, creating parent directories."""

        config_path = Path(path) if path else Path(self.config_path)
        if not config_path.is_absolute():
            config_path = _REPO_ROOT / config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.config_path = str(config_path)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        """Build a config from a (possibly older) JSON dict.

        Unknown keys are ignored and missing keys fall back to defaults, so a
        v1 ``config.json`` upgrades transparently.
        """

        models = ModelConfig(**_pick(ModelConfig, data.get("models") or {}))
        llm = LLMConfig(**_pick(LLMConfig, data.get("llm") or {}))
        analysis = AnalysisConfig(**_pick(AnalysisConfig, data.get("analysis") or {}))
        top = _pick(AppConfig, data)
        top.pop("models", None)
        top.pop("llm", None)
        top.pop("analysis", None)
        if "font_size" in top:
            top["font_size"] = _coerce_font_size(top["font_size"])
        if "font_family" in top:
            top["font_family"] = _coerce_font_family(top["font_family"])
        return cls(models=models, llm=llm, analysis=analysis, **top)


def _coerce_font_size(value: Any) -> int:
    """Clamp a user supplied font size into ``[9, 24]``.

    Non numeric values (strings, ``None``, booleans, ...) fall back to the
    default so a malformed ``config.json`` never breaks startup.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _DEFAULT_FONT_SIZE
    return max(_MIN_FONT_SIZE, min(_MAX_FONT_SIZE, int(value)))


def _coerce_font_family(value: Any) -> str:
    """Return a usable font family name, or "" for the application default."""

    if isinstance(value, str):
        return value
    return ""


def _pick(dataclass_type: type, data: dict[str, Any]) -> dict[str, Any]:
    """Keep only keys that correspond to fields of ``dataclass_type``."""

    known = {f.name for f in fields(dataclass_type)}
    return {key: value for key, value in data.items() if key in known}
