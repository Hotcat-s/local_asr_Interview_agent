"""Runtime wiring shared by every API route.

The sidecar owns exactly one :class:`AppState`: SQLite repository, event bus,
serial task queue and a lazily created :class:`InterviewEngine`.  Keeping this
state in one object makes the FastAPI app easy to test and keeps the core layer
free of any web-framework imports.
"""

from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

from core.config import AppConfig
from core.engine import InterviewEngine
from core.storage.repository import Repository

from backend.services.events import EventBus
from backend.services.tasks import TaskQueue

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RuntimePaths:
    data_dir: Path
    audio_dir: Path
    config_path: Path
    db_path: Path

    @classmethod
    def resolve(cls, data_dir: str | None) -> "RuntimePaths":
        root = Path(data_dir).expanduser().resolve() if data_dir else REPO_ROOT / "data"
        audio_dir = root / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        paths = cls(
            data_dir=root,
            audio_dir=audio_dir,
            config_path=root / "config.json",
            db_path=root / "interview.db",
        )
        paths._seed_legacy_config()
        return paths

    def _seed_legacy_config(self) -> None:
        """Copy the old repository-level config on first run."""

        if self.config_path.exists():
            return
        legacy = REPO_ROOT / "config.json"
        if legacy.exists():
            shutil.copy2(legacy, self.config_path)
            logger.info("Seeded %s from legacy config", self.config_path)


class AppState:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self.config = self._load_config()
        self.repo = Repository(str(paths.db_path))
        self.events = EventBus()
        self.tasks = TaskQueue(self)
        self._engine: InterviewEngine | None = None
        self._engine_lock = threading.Lock()

    def _load_config(self) -> AppConfig:
        config = AppConfig.load(str(self.paths.config_path))
        config.data_dir = str(self.paths.data_dir)
        config.db_path = str(self.paths.db_path)
        config.config_path = str(self.paths.config_path)
        return config

    @property
    def engine_loaded(self) -> bool:
        return self._engine is not None

    def engine(self) -> InterviewEngine:
        with self._engine_lock:
            if self._engine is None:
                self._engine = InterviewEngine(self.config)
            return self._engine

    def set_engine(self, engine: InterviewEngine | None) -> None:
        """Replace the engine; used by tests and by ``/models/reload``."""

        with self._engine_lock:
            self._engine = engine

    def unload_engine(self) -> None:
        with self._engine_lock:
            if self._engine is not None:
                self._engine.unload()
            self._engine = None

    def update_config(self, config: AppConfig) -> AppConfig:
        config.data_dir = str(self.paths.data_dir)
        config.db_path = str(self.paths.db_path)
        config.config_path = str(self.paths.config_path)
        config.save(str(self.paths.config_path))
        self.config = config
        # Model / segmentation settings are captured by the engine at build
        # time, so drop the cached instance and let the next task rebuild it.
        self.unload_engine()
        return config

    def shutdown(self) -> None:
        self.tasks.stop()
        self.unload_engine()
        self.repo.close()
