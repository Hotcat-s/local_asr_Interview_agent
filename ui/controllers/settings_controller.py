"""配置读写与 LLM 连接测试的桥接控制器。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, Slot

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.config import AnalysisConfig, AppConfig, LLMConfig, ModelConfig

logger = logging.getLogger(__name__)


class _TestWorker(QObject):
    """在子线程中执行 LLM 连接测试，避免网络等待阻塞主线程。"""

    finished = Signal(bool, str)

    def __init__(self, llm_config: "LLMConfig", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = llm_config

    @Slot()
    def run(self) -> None:
        try:
            from core.llm.client import LLMClient  # noqa: PLC0415

            ok, message = LLMClient(self._config).test_connection()
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM 连接测试失败")
            ok, message = False, str(exc) or exc.__class__.__name__
        self.finished.emit(ok, message)


class SettingsController(QObject):
    """加载 / 保存 :class:`core.config.AppConfig`，并提供异步连接测试。"""

    config_saved = Signal(object)  # AppConfig
    test_finished = Signal(bool, str)

    def __init__(self, config: "AppConfig | None" = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._thread: QThread | None = None
        self._worker: _TestWorker | None = None

    def config(self) -> "AppConfig":
        if self._config is None:
            from core.config import AppConfig  # noqa: PLC0415

            self._config = AppConfig.load()
        return self._config

    def save(
        self,
        llm_config: "LLMConfig",
        model_config: "ModelConfig | None" = None,
        analysis_config: "AnalysisConfig | None" = None,
        *,
        theme: str | None = None,
        font_family: str | None = None,
        font_size: int | None = None,
    ) -> None:
        config = self.config()
        config.llm = llm_config
        if model_config is not None:
            config.models = model_config
        if analysis_config is not None:
            config.analysis = analysis_config
        if theme is not None:
            config.theme = theme
        # 字体字段由 core 在 v5 新增；用 setattr/getattr 兼容旧版本 core（字段缺失时
        # 仍可写入内存配置，不抛异常）。
        if font_family is not None:
            setattr(config, "font_family", str(font_family).strip())
        if font_size is not None:
            from ui import theme as ui_theme  # noqa: PLC0415

            setattr(config, "font_size", ui_theme.clamp_font_size(font_size))
        config.save()
        self.config_saved.emit(config)

    def test_connection(self, llm_config: "LLMConfig") -> None:
        if self._thread is not None:
            return
        thread = QThread(self)
        worker = _TestWorker(llm_config)
        worker.moveToThread(thread)
        worker.finished.connect(self._on_test_finished)
        thread.started.connect(worker.run)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(bool, str)
    def _on_test_finished(self, ok: bool, message: str) -> None:
        self.test_finished.emit(ok, message)
        thread = self._thread
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self._worker = None
        self._thread = None
