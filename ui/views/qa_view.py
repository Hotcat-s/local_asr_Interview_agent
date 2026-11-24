"""问答对视图：展示并编辑 ``core.schemas.QAPair`` 列表。

列：序号(只读) / 问题(可编辑) / 回答(可编辑)。编辑后发出 :attr:`qa_edited`，
由主窗口负责持久化。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget

from ui.models.qa_model import QATableModel
from ui.views.table import EditableTableView

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.schemas import QAPair


class QAView(QWidget):
    """按时间顺序排列、可编辑的 Q/A 表格。"""

    qa_edited = Signal(int)  # QAPair 列表位置

    def __init__(self, parent: QWidget | None = None, theme_name: str = "dark") -> None:
        super().__init__(parent)
        self._model = QATableModel(self)
        self._table = EditableTableView(self)
        self._table.setModel(self._model)
        self._table.set_column_widths([60, 380, 420])
        self._table.attach_edit_signal()
        self._table.cell_edited.connect(self.qa_edited)
        self._table.set_wrapping_columns([1, 2])  # 问题 / 回答列可能换行
        self._table.set_theme_name(theme_name)

        self._placeholder = QLabel("暂无问答对，完成转写后自动生成。", self)
        self._placeholder.setAlignment(Qt.AlignCenter)

        self._stack = QStackedLayout(self)
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._table)
        self._stack.setCurrentWidget(self._placeholder)

    def set_qa_pairs(self, pairs: "list[QAPair] | None") -> None:
        self._model.set_qa_pairs(pairs)
        has_rows = self._model.rowCount() > 0
        self._stack.setCurrentWidget(self._table if has_rows else self._placeholder)
        if has_rows:
            self._table.schedule_resize()

    def qa_pairs(self) -> "list[QAPair]":
        return self._model.qa_pairs()

    def set_theme_name(self, theme_name: str) -> None:
        self._table.set_theme_name(theme_name)

    def set_font(self, family: str = "", size: int = 12) -> None:
        """套用主要内容区字体（表格 + 占位提示）。"""

        from ui import theme  # noqa: PLC0415

        self._table.set_font(family, size)
        theme.apply_font(self._placeholder, family, size)

    def clear(self) -> None:
        self.set_qa_pairs(None)
