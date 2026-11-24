"""左侧录音库面板：搜索、状态筛选、列表与右键操作。

这是**唯一的导入入口**。右键菜单支持：打开 / 重命名 / 重新转写 / 删除。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import Action, ComboBox, RoundMenu, SearchLineEdit

from ui import theme
from ui.models.library_model import LibraryModel, _get
from ui.models.transcript_model import format_timestamp
from ui.views.widgets import AccentButton, SectionTitle

_STATUS_FILTERS: list[tuple[str, str]] = [
    ("", "全部"),
    ("imported", "待转写"),
    ("transcribed", "已转写"),
    ("analyzed", "已完成"),
    ("failed", "处理失败"),
]


class _LibraryDelegate(QStyledItemDelegate):
    """绘制两行列表项：标题 + 元信息，右侧状态徽章。"""

    def __init__(self, theme_name: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name

    def set_theme_name(self, theme_name: str) -> None:
        self._theme_name = theme_name

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), 56)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item = index.data(LibraryModel.RecordingRole)
        if item is None:
            super().paint(painter, option, index)
            return

        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        pal = theme.palette(self._theme_name)

        if selected:
            painter.fillRect(rect, QColor(pal["selection"]))
            painter.setPen(QPen(QColor(pal["accent"]), 2))
            painter.drawLine(rect.left(), rect.top() + 6, rect.left(), rect.bottom() - 6)
        elif hovered:
            painter.fillRect(rect, QColor(pal["panel_alt"]))

        pad = 12
        right = rect.right() - pad
        title_rect = QRect(rect.left() + pad, rect.top() + 8, rect.width() - 2 * pad, 20)
        meta_rect = QRect(rect.left() + pad, rect.top() + 30, rect.width() - 2 * pad, 18)

        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(pal["text"]))
        title = str(_get(item, "title", "") or "未命名录音")
        painter.drawText(
            title_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            painter.fontMetrics().elidedText(title, Qt.ElideRight, title_rect.width()),
        )

        status = str(_get(item, "status", "") or "")
        badge_text = theme.status_label(status)
        badge_color = QColor(theme.status_color(status, self._theme_name))
        badge_font = QFont(option.font)
        badge_font.setPointSizeF(max(8.0, option.font.pointSizeF() - 2))
        badge_font.setBold(True)
        painter.setFont(badge_font)
        badge_w = painter.fontMetrics().horizontalAdvance(badge_text) + 18
        badge_h = 18
        badge_rect = QRect(right - badge_w, rect.top() + 9, badge_w, badge_h)
        painter.setPen(QPen(badge_color, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(badge_rect, 9, 9)
        painter.setPen(badge_color)
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        duration = float(_get(item, "duration", 0.0) or 0.0)
        meta = format_timestamp(duration) if duration else "时长未知"
        created = str(_get(item, "created_at", "") or "")
        if created:
            meta = f"{meta} · {created[:16].replace('T', ' ')}"
        painter.setFont(option.font)
        painter.setPen(QColor(pal["text_muted"]))
        painter.drawText(
            meta_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            painter.fontMetrics().elidedText(meta, Qt.ElideRight, meta_rect.width() - badge_w - 6),
        )
        painter.restore()


class LibraryPanel(QWidget):
    """录音库侧边栏。"""

    open_requested = Signal(int)
    delete_requested = Signal(int)
    rename_requested = Signal(int)
    retranscribe_requested = Signal(int)
    import_requested = Signal()
    filter_changed = Signal(str, str)  # (search_text, status_filter)

    def __init__(self, theme_name: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidePanel")
        self._theme_name = theme_name

        self._search = SearchLineEdit(self)
        self._search.setPlaceholderText("搜索录音…")
        self._search.setClearButtonEnabled(True)

        self._filter = ComboBox(self)
        for value, label in _STATUS_FILTERS:
            self._filter.addItem(label, userData=value)

        self._import_button = AccentButton("＋ 导入音频", self)

        self._model = LibraryModel(self)
        self._delegate = _LibraryDelegate(theme_name, self)
        self._view = QListView(self)
        self._view.setModel(self._model)
        self._view.setItemDelegate(self._delegate)
        self._view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._view.setUniformItemSizes(True)
        self._view.setMouseTracking(True)
        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(SectionTitle("录音库", self))
        header.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self._import_button)
        layout.addWidget(self._search)
        layout.addWidget(self._filter)
        layout.addWidget(self._view, 1)

        self._import_button.clicked.connect(self.import_requested)
        self._search.textChanged.connect(self._emit_search)
        self._filter.currentIndexChanged.connect(self._emit_search)
        # 单击（含键盘上下键切换）即打开：绑定到选中变化，而非双击。
        # 双击会先触发 currentChanged，因此双击场景天然可用且不会重复。
        self._last_emitted_id: int | None = None
        self._view.selectionModel().currentChanged.connect(self._on_current_changed)
        self._view.customContextMenuRequested.connect(self._on_context_menu)
        self._apply_view_style()

    # ---- 对外 API ----
    def set_recordings(self, items: list[Any] | None) -> None:
        self._model.set_recordings(items)
        # 模型重置会清空选中；重置去重记忆，保证刷新后再次选中同一行仍能打开。
        self._last_emitted_id = None

    def select_recording(self, recording_id: int) -> None:
        row = self._model.row_of_id(recording_id)
        if row >= 0:
            index = self._model.index(row)
            self._view.setCurrentIndex(index)
            self._view.scrollTo(index, QAbstractItemView.PositionAtCenter)

    def current_id(self) -> int | None:
        index = self._view.currentIndex()
        if not index.isValid():
            return None
        value = index.data(Qt.UserRole)
        return int(value) if value is not None else None

    def search_text(self) -> str:
        return self._search.text().strip()

    def status_filter(self) -> str:
        return str(self._filter.currentData() or "")

    def set_theme_name(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self._delegate.set_theme_name(theme_name)
        self._apply_view_style()
        self._view.viewport().update()

    def _apply_view_style(self) -> None:
        pal = theme.palette(self._theme_name)
        self._view.setStyleSheet(
            f"QListView {{ background-color: {pal['panel']}; border: none; }}"
            "QListView::item { background: transparent; }"
        )

    # ---- 内部 ----
    def _emit_search(self) -> None:
        self.filter_changed.emit(self.search_text(), self.status_filter())

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """选中变化即请求打开；按“上次已发出 id”去重，避免重复/递归加载。"""

        if not current.isValid():
            return
        value = current.data(Qt.UserRole)
        if value is None:
            return
        recording_id = int(value)
        if recording_id == self._last_emitted_id:
            return
        self._last_emitted_id = recording_id
        self.open_requested.emit(recording_id)

    def _build_context_menu(self, recording_id: int) -> RoundMenu:
        """构建右键菜单并把每项绑定到对应信号。

        qfluentwidgets 的 ``RoundMenu.exec()`` **没有返回值**（恒为 ``None``），
        因此不能用返回值判断选中项；这里改为用 ``Action.triggered`` 信号回调。
        回调用 ``*_args`` 吞掉 ``triggered`` 携带的 ``checked`` 布尔参数。
        """

        menu = RoundMenu(parent=self)

        def bind(action: Action, signal) -> Action:
            action.triggered.connect(lambda *_args, _sig=signal: _sig.emit(recording_id))
            menu.addAction(action)
            return action

        bind(Action("打开", menu), self.open_requested)
        bind(Action("重命名", menu), self.rename_requested)
        bind(Action("重新转写", menu), self.retranscribe_requested)
        menu.addSeparator()
        bind(Action("删除", menu), self.delete_requested)
        return menu

    def _on_context_menu(self, pos) -> None:
        index = self._view.indexAt(pos)
        if not index.isValid():
            return
        recording_id = index.data(Qt.UserRole)
        if recording_id is None:
            return
        menu = self._build_context_menu(int(recording_id))
        menu.exec(self._view.viewport().mapToGlobal(pos))
