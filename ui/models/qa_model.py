"""问答对表格模型：适配 ``core.schemas.QAPair``，支持单元格编辑。

列：序号 / 问题 / 回答。“序号”只读，“问题”“回答”可编辑；编辑后就地写回
内存中的 :class:`~core.schemas.QAPair`，并通过 ``dataChanged`` 通知视图。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.schemas import QAPair

_EDITABLE_COLUMNS = {1, 2}


class QATableModel(QAbstractTableModel):
    """列：序号 / 问题 / 回答；问题与回答列可编辑。"""

    HEADERS = ("序号", "问题", "回答")

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._pairs: list["QAPair"] = []

    def set_qa_pairs(self, pairs: "list[QAPair] | None") -> None:
        self.beginResetModel()
        self._pairs = list(pairs) if pairs else []
        self.endResetModel()

    def qa_pairs(self) -> list["QAPair"]:
        return self._pairs

    # ---- QAbstractTableModel ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._pairs)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> Any:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = super().flags(index)
        if index.isValid() and index.column() in _EDITABLE_COLUMNS:
            return base | Qt.ItemIsEditable
        return base

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._pairs)):
            return None
        pair = self._pairs[index.row()]
        column = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if column == 0:
                return str(pair.index + 1)
            if column == 1:
                return pair.question
            if column == 2:
                return pair.answer
        elif role == Qt.ToolTipRole:
            if column == 1:
                return pair.question
            if column == 2:
                return pair.answer
            return f"{pair.question_speaker} → {pair.answer_speaker}"
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:  # noqa: N802
        if role != Qt.EditRole or not index.isValid():
            return False
        if index.column() not in _EDITABLE_COLUMNS:
            return False
        if not (0 <= index.row() < len(self._pairs)):
            return False
        text = str(value)
        pair = self._pairs[index.row()]
        if index.column() == 1:
            if text == pair.question:
                return False
            pair.question = text
        else:
            if text == pair.answer:
                return False
            pair.answer = text
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True
