"""转写结果表格模型：适配 ``core.schemas.Transcript``，支持单元格编辑。

列：时间 / 说话人 / 内容。仅“内容”列可编辑；编辑后就地写回内存中的
:class:`~core.schemas.TranscriptSegment`，并通过 ``dataChanged`` 通知视图。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.schemas import Transcript, TranscriptSegment

_EDITABLE_COLUMNS = {2}


def format_timestamp(seconds: float) -> str:
    """将秒数格式化为 ``mm:ss`` 或 ``hh:mm:ss``。"""

    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class TranscriptTableModel(QAbstractTableModel):
    """列：时间 / 说话人 / 内容；内容列可编辑。"""

    HEADERS = ("时间", "说话人", "内容")

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._segments: list["TranscriptSegment"] = []
        self._duration: float = 0.0
        self._language: str = "zh"

    # ---- 数据装载 ----
    def set_transcript(self, transcript: "Transcript | None") -> None:
        self.beginResetModel()
        if transcript is not None:
            self._segments = list(transcript.segments)
            self._duration = float(getattr(transcript, "duration", 0.0) or 0.0)
            self._language = str(getattr(transcript, "language", "zh") or "zh")
        else:
            self._segments = []
            self._duration = 0.0
            self._language = "zh"
        self.endResetModel()

    def segments(self) -> list["TranscriptSegment"]:
        return self._segments

    def transcript(self) -> "Transcript":
        """按当前（可能已编辑）的段落重建一个 :class:`~core.schemas.Transcript`。"""

        from core.schemas import Transcript  # noqa: PLC0415

        raw_text = " ".join(seg.text.strip() for seg in self._segments if seg.text.strip())
        return Transcript(
            segments=list(self._segments),
            duration=self._duration,
            language=self._language,
            raw_text=raw_text,
        )

    # ---- QAbstractTableModel ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._segments)

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
        if not index.isValid() or not (0 <= index.row() < len(self._segments)):
            return None
        segment = self._segments[index.row()]
        column = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if column == 0:
                return format_timestamp(segment.start)
            if column == 1:
                return segment.speaker
            if column == 2:
                return segment.text
        elif role == Qt.ToolTipRole:
            return (
                f"{format_timestamp(segment.start)} - "
                f"{format_timestamp(segment.end)} · {segment.speaker}"
            )
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:  # noqa: N802
        if role != Qt.EditRole or not index.isValid():
            return False
        if index.column() not in _EDITABLE_COLUMNS:
            return False
        if not (0 <= index.row() < len(self._segments)):
            return False
        text = str(value)
        segment = self._segments[index.row()]
        if text == segment.text:
            return False
        segment.text = text
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True
