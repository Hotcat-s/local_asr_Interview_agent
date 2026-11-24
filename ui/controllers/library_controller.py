"""录音库控制器：封装所有本地持久化操作。

视图层只与本控制器交互，绝不直接触碰 ``core.storage.Repository``。
所有 CRUD 均通过懒加载的 Repository 完成，并对异常做统一上报。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.schemas import InterviewReport, QAPair, Recording, RecordingDetail, Transcript

logger = logging.getLogger(__name__)


class LibraryController(QObject):
    """录音库的增删查与状态流转。"""

    library_changed = Signal()  # 列表需要刷新
    recording_opened = Signal(object)  # core.RecordingDetail
    error = Signal(str)

    def __init__(self, db_path: str = "data/interview.db", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._repo = None

    # ---- 基础设施 ----
    def _repository(self):
        if self._repo is None:
            from core.storage.repository import Repository  # noqa: PLC0415

            self._repo = Repository(self._db_path)
        return self._repo

    def set_db_path(self, path: str) -> None:
        if path and path != self._db_path:
            if self._repo is not None:
                try:
                    self._repo.close()
                except Exception:  # noqa: BLE001
                    pass
            self._db_path = path
            self._repo = None

    def _guard(self, action: str, func, *args: Any, default: Any = None, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s 失败", action)
            self.error.emit(f"{action}失败：{exc}")
            return default

    # ---- 查询 ----
    def refresh(self, status: str | None = None, search: str | None = None) -> list:
        repo = self._repository()
        items = self._guard(
            "加载录音库",
            repo.list_recordings,
            status=status or None,
            search=search or None,
            default=[],
        )
        return list(items or [])

    def get_recording(self, recording_id: int) -> "Recording | None":
        return self._guard("读取录音", self._repository().get_recording, recording_id)

    def counts(self) -> dict:
        return self._guard("统计录音", self._repository().count_recordings, default={}) or {}

    # ---- 变更 ----
    def import_audio(self, audio_path: str, title: str = "") -> int:
        resolved_title = title.strip() or os.path.basename(audio_path) or "未命名录音"
        recording_id = self._repository().create_recording(resolved_title, audio_path)
        self.library_changed.emit()
        return int(recording_id)

    def open_recording(self, recording_id: int) -> None:
        detail = self._guard("打开录音", self._repository().get_detail, recording_id)
        if detail is not None:
            self.recording_opened.emit(detail)

    def delete_recording(self, recording_id: int) -> None:
        self._guard("删除录音", self._repository().delete_recording, recording_id)
        self.library_changed.emit()

    def set_status(self, recording_id: int, status: str, error: str = "") -> None:
        self._guard(
            "更新状态",
            self._repository().update_status,
            recording_id,
            status,
            error_message=error,
        )
        self.library_changed.emit()

    def save_transcript(self, recording_id: int, transcript: "Transcript") -> None:
        self._guard("保存转写", self._repository().save_transcript, recording_id, transcript)
        self.library_changed.emit()

    def save_qa_pairs(self, recording_id: int, qa_pairs: "list[QAPair]") -> None:
        self._guard("保存问答对", self._repository().save_qa_pairs, recording_id, qa_pairs)
        self.library_changed.emit()

    def save_report(self, recording_id: int, report: "InterviewReport") -> None:
        self._guard("保存报告", self._repository().save_report, recording_id, report)
        self._guard(
            "标记已分析",
            self._repository().mark_analyzed,
            recording_id,
            report.overall_score,
        )
        self.library_changed.emit()

    # ---- v3 新增 ----
    def rename_recording(self, recording_id: int, title: str) -> None:
        """重命名录音。优先用 Repository.rename_recording，缺失时回退到 update_metadata。"""

        clean = (title or "").strip()
        if not clean:
            return
        repo = self._repository()

        def _rename() -> None:
            rename = getattr(repo, "rename_recording", None)
            if callable(rename):
                rename(recording_id, clean)
            else:
                repo.update_metadata(recording_id, title=clean)

        self._guard("重命名录音", _rename)
        self.library_changed.emit()

    def update_transcript(self, recording_id: int, transcript: "Transcript") -> None:
        """保存编辑后的转写文本。"""

        self._guard("保存转写", self._repository().save_transcript, recording_id, transcript)
        self.library_changed.emit()

    def update_qa_pairs(self, recording_id: int, qa_pairs: "list[QAPair]") -> None:
        """保存编辑后的问答对。"""

        self._guard("保存问答对", self._repository().save_qa_pairs, recording_id, qa_pairs)
        self.library_changed.emit()

    def rebuild_qa_pairs(self, recording_id: int, transcript: "Transcript") -> list:
        """依据转写文本重建问答对并落库，返回新列表。

        使用纯 Python 的 :class:`core.diarization.qa_builder.QABuilder`（不加载模型），
        并优先用 :mod:`core.editing` 规范化序号。
        """

        def _build() -> list:
            from core.diarization.qa_builder import QABuilder  # noqa: PLC0415

            pairs = QABuilder().build(transcript)
            try:
                from core.editing import normalize_qa_pairs  # noqa: PLC0415

                pairs = normalize_qa_pairs(pairs)
            except Exception:  # noqa: BLE001 - core.editing 未就绪时保持原样
                pass
            self._repository().save_qa_pairs(recording_id, pairs)
            return list(pairs)

        result = self._guard("重建问答对", _build, default=[])
        self.library_changed.emit()
        return list(result or [])
