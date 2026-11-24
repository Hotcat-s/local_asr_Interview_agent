"""录音库列表模型：适配 ``core.schemas.Recording``。

同时兼容 dataclass 属性访问与 dict 键访问，方便在测试中注入假数据。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


def _get(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


class LibraryModel(QAbstractListModel):
    """把录音列表暴露给 ``QListView``。"""

    RecordingRole = Qt.UserRole + 1

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._items: list[Any] = []

    # ---- 数据 ----
    def set_recordings(self, items: list[Any] | None) -> None:
        self.beginResetModel()
        self._items = list(items) if items else []
        self.endResetModel()

    def recordings(self) -> list[Any]:
        return self._items

    def recording_at(self, row: int) -> Any | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def row_of_id(self, recording_id: int) -> int:
        for row, item in enumerate(self._items):
            if int(_get(item, "id", -1)) == int(recording_id):
                return row
        return -1

    # ---- QAbstractListModel ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == Qt.DisplayRole:
            return str(_get(item, "title", "") or "未命名录音")
        if role == Qt.ToolTipRole:
            return str(_get(item, "audio_path", ""))
        if role == self.RecordingRole:
            return item
        if role == Qt.UserRole:
            return int(_get(item, "id", -1))
        return None
