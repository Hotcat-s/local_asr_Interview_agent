"""转写 / 分析任务控制器（v2：两阶段严格解耦）。

- 阶段一 :meth:`AnalysisController.transcribe` 只做本地 ASR，产出 ``Transcript``；
- 阶段二 :meth:`AnalysisController.analyze` 只做 LLM 复盘，产出 ``InterviewReport``；
  两者互不自动触发，均由 UI 主动调用。
- 所有耗时调用都在独立 ``QThread`` 中执行，通过信号回主线程。
- ``cancel`` 设置线程安全标志，worker 在 progress 回调中检查并抛出取消异常。
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.config import AppConfig, LLMConfig
    from core.engine import InterviewEngine
    from core.progress import ProgressEvent
    from core.schemas import InterviewReport, Transcript

logger = logging.getLogger(__name__)


class CanceledError(Exception):
    """本地取消异常；core 提供 ``CancelledError`` 时以其为准。"""


def _resolve_cancel_types() -> tuple[tuple[type[BaseException], ...], type[BaseException]]:
    """返回 (可捕获的取消异常类型元组, 用于抛出的取消异常类型)。"""

    types: list[type[BaseException]] = [CanceledError]
    raise_type: type[BaseException] = CanceledError
    try:
        from core.exceptions import CancelledError as CoreCancelled  # noqa: PLC0415

        types.append(CoreCancelled)
        raise_type = CoreCancelled
    except Exception:  # noqa: BLE001 - core 未就绪时用本地异常
        pass
    return tuple(types), raise_type


_CANCELLED_TYPES, _CANCEL_ERROR = _resolve_cancel_types()


class AnalysisWorker(QObject):
    """在子线程中执行单个 core 任务。"""

    progress = Signal(object)  # core.ProgressEvent
    transcribed = Signal(object)  # core.Transcript
    analyzed = Signal(object)  # core.InterviewReport
    error = Signal(str)
    canceled = Signal()
    done = Signal()

    def __init__(self, engine: "InterviewEngine", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._cancel = threading.Event()
        self._task = "transcribe"
        self._args: tuple[Any, ...] = ()

    def prepare(self, task: str, *args: Any) -> None:
        self._task = task
        self._args = args

    def request_cancel(self) -> None:
        self._cancel.set()

    def _on_progress(self, event: "ProgressEvent") -> None:
        if self._cancel.is_set():
            raise _CANCEL_ERROR("任务已取消")
        self.progress.emit(event)

    @Slot()
    def execute(self) -> None:
        try:
            if self._cancel.is_set():
                raise _CANCEL_ERROR("任务已取消")

            if self._task == "transcribe":
                audio_path, chunk_seconds = self._args
                transcript = self._engine.transcribe(
                    audio_path,
                    progress=self._on_progress,
                    chunk_seconds=chunk_seconds,
                )
                self.transcribed.emit(transcript)
            elif self._task == "analyze":
                qa_pairs, llm_config = self._args
                report = self._engine.analyze(
                    qa_pairs,
                    llm_config=llm_config,
                    progress=self._on_progress,
                )
                self.analyzed.emit(report)
            else:
                raise ValueError(f"未知任务类型: {self._task}")
        except _CANCELLED_TYPES:  # type: ignore[misc]
            logger.info("任务已取消: %s", self._task)
            self.canceled.emit()
        except Exception as exc:  # noqa: BLE001 - 统一反馈给 UI
            logger.exception("任务执行失败: %s", self._task)
            self.error.emit(str(exc) or exc.__class__.__name__)
        finally:
            self.done.emit()


class AnalysisController(QObject):
    """面向主窗口的两阶段任务调度器。"""

    progress = Signal(object)  # core.ProgressEvent
    transcribed = Signal(object)  # core.Transcript
    analyzed = Signal(object)  # core.InterviewReport
    error = Signal(str)
    canceled = Signal()
    busy_changed = Signal(bool)
    stage_changed = Signal(str)  # "transcribe" | "analyze" | ""

    def __init__(
        self,
        engine: "InterviewEngine | None" = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config: "AppConfig | None" = None
        self._engine = engine
        self._owns_engine = engine is None
        self._thread: QThread | None = None
        self._worker: AnalysisWorker | None = None
        self._busy = False
        self._stage = ""

    # ---- 配置 ----
    def set_config(self, config: "AppConfig") -> None:
        self._config = config
        if self._owns_engine:
            self._engine = None

    def _ensure_engine(self) -> "InterviewEngine":
        if self._engine is None:
            from core.engine import InterviewEngine  # noqa: PLC0415

            self._engine = InterviewEngine(self._config)
        return self._engine

    # ---- 公共任务接口 ----
    def transcribe(self, audio_path: str) -> None:
        chunk = getattr(self._config, "chunk_seconds", None) if self._config is not None else None
        self._start("transcribe", audio_path, chunk)

    def analyze(self, qa_pairs: list[Any], llm_config: "LLMConfig | None") -> None:
        self._start("analyze", qa_pairs, llm_config)

    def build_qa(self, transcript: "Transcript") -> list[Any]:
        """同步调用 core 的纯计算 Q/A 配对（快，无需线程）。"""

        try:
            return self._ensure_engine().build_qa(transcript)
        except Exception:  # noqa: BLE001
            logger.exception("Q/A 配对失败")
            return []

    def unload_models(self) -> None:
        if self._engine is not None:
            try:
                self._engine.unload()
            except Exception:  # noqa: BLE001
                logger.exception("卸载模型失败")

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()

    def is_busy(self) -> bool:
        return self._busy

    def current_stage(self) -> str:
        return self._stage

    # ---- 内部实现 ----
    def _start(self, task: str, *args: Any) -> None:
        if self._busy:
            self.error.emit("已有任务正在运行，请先取消或等待完成。")
            return
        try:
            engine = self._ensure_engine()
        except Exception as exc:  # noqa: BLE001
            logger.exception("初始化引擎失败")
            self.error.emit(f"初始化引擎失败：{exc}")
            return

        thread = QThread(self)
        worker = AnalysisWorker(engine)
        worker.moveToThread(thread)
        worker.prepare(task, *args)

        worker.progress.connect(self.progress)
        worker.transcribed.connect(self.transcribed)
        worker.analyzed.connect(self.analyzed)
        worker.error.connect(self.error)
        worker.canceled.connect(self.canceled)
        worker.done.connect(self._on_done)
        thread.started.connect(worker.execute)

        self._thread = thread
        self._worker = worker
        self._stage = task
        self.stage_changed.emit(task)
        self._set_busy(True)
        thread.start()

    @Slot()
    def _on_done(self) -> None:
        thread = self._thread
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self._worker = None
        self._thread = None
        self._stage = ""
        self.stage_changed.emit("")
        self._set_busy(False)

    def _set_busy(self, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busy_changed.emit(value)
