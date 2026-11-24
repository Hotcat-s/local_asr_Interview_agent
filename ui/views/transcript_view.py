"""转写文本视图：展示并编辑 ``core.schemas.Transcript``。

列：时间(只读) / 说话人(只读) / 内容(可编辑)。编辑内容后发出
:attr:`transcript_edited`，由主窗口负责持久化与后续同步。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget

from ui.models.transcript_model import TranscriptTableModel
from ui.views.table import EditableTableView

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.schemas import Transcript


class TranscriptView(QWidget):
    """可编辑的逐句转写表格；无数据时显示占位提示。"""

    transcript_edited = Signal(int)  # 段落序号

    def __init__(self, parent: QWidget | None = None, theme_name: str = "dark") -> None:
        super().__init__(parent)
        self._model = TranscriptTableModel(self)
        self._table = EditableTableView(self)
        self._table.setModel(self._model)
        self._table.set_column_widths([90, 90, 640])
        self._table.attach_edit_signal()
        self._table.cell_edited.connect(self.transcript_edited)
        self._table.set_wrapping_columns([2])  # 仅“内容”列含长文本
        self._table.set_theme_name(theme_name)

        self._placeholder = QLabel("暂无转写文本，点击「开始转写」生成。", self)
        self._placeholder.setAlignment(Qt.AlignCenter)

        self._stack = QStackedLayout(self)
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._table)
        self._stack.setCurrentWidget(self._placeholder)

    def set_transcript(self, transcript: "Transcript | None") -> None:
        self._model.set_transcript(transcript)
        has_rows = self._model.rowCount() > 0
        self._stack.setCurrentWidget(self._table if has_rows else self._placeholder)
        if has_rows:
            self._table.schedule_resize()

    def transcript(self) -> "Transcript":
        return self._model.transcript()

    def set_theme_name(self, theme_name: str) -> None:
        self._table.set_theme_name(theme_name)

    def set_font(self, family: str = "", size: int = 12) -> None:
        """套用主要内容区字体（表格 + 占位提示）。"""

        from ui import theme  # noqa: PLC0415

        self._table.set_font(family, size)
        theme.apply_font(self._placeholder, family, size)

    def clear(self) -> None:
        self.set_transcript(None)
