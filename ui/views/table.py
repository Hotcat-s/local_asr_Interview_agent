"""可编辑表格基类：统一“文字完整显示 + 列宽/行高可自由拖动”的行为。

``TranscriptView`` 与 ``QAView`` 共用此类，避免重复设置视图参数。
编辑完成（``dataChanged``）时发出 :attr:`cell_edited`，携带被编辑行号。

行高**按需**计算：不再对整个表格无条件调用 ``resizeRowsToContents()``（该调用对
每一行都测换行文本，复杂度 O(行数 × 文本长度)）。这里改为：

* 用 :class:`_WrappingRowDelegate` 负责“一个单元格需要多高”的计算；
* 视图只在**数据载入**、**某几行被编辑**、**列宽变化**时，针对受影响的行调用
  ``setRowHeight``，避免整表 O(n) 重算。

同时仍保证 v3 契约“文字完整显示”：``setWordWrap(True)``、行高按换行文本实测高度
自适应、列宽可拖动、横向可滚动。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from ui import theme


class _WrappingRowDelegate(QStyledItemDelegate):
    """按单元格文本换行后的实测高度计算行高（Qt 只对需要它的单元格求值）。"""

    MIN_ROW_HEIGHT = 34
    VERTICAL_PADDING = 14
    HORIZONTAL_PADDING = 16
    WRAP_FLAGS = int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802
        view = self.parent()
        width = option.rect.width()
        if width <= 0 and isinstance(view, QTableView):
            width = view.columnWidth(index.column())
        metrics = QFontMetrics(option.font)
        height = self.height_for_metrics(metrics, width, index.data(Qt.DisplayRole))
        return QSize(width, height)

    def wrapped_height(self, font: QFont, width: int, text: object) -> int:
        """返回 ``text`` 在给定列宽下换行显示所需的最小行高。"""

        return self.height_for_metrics(QFontMetrics(font), width, text)

    def base_height(self, metrics: QFontMetrics) -> int:
        """单行文本所需的最小行高（随字体大小缩放，避免大字号被裁切）。"""

        return max(self.MIN_ROW_HEIGHT, metrics.height() + self.VERTICAL_PADDING)

    def height_for_metrics(self, metrics: QFontMetrics, width: int, text: object) -> int:
        """使用预先构造的 ``QFontMetrics`` 计算换行高度（批量重算时复用）。"""

        available = max(40, int(width) - self.HORIZONTAL_PADDING)
        rect = metrics.boundingRect(
            QRect(0, 0, available, 100000), self.WRAP_FLAGS, str(text or "")
        )
        return max(self.base_height(metrics), rect.height() + self.VERTICAL_PADDING)


class EditableTableView(QTableView):
    """支持按需行高自适应、可拖动列宽/行高、横向滚动的表格。"""

    cell_edited = Signal(int)  # 被编辑的行号

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self._theme_name = "dark"
        self._delegate = _WrappingRowDelegate(self)
        self.setItemDelegate(self._delegate)

        vertical = self.verticalHeader()
        vertical.setVisible(True)
        vertical.setSectionResizeMode(QHeaderView.Interactive)
        vertical.setDefaultSectionSize(46)
        vertical.setMinimumSectionSize(30)

        horizontal = self.horizontalHeader()
        horizontal.setSectionResizeMode(QHeaderView.Interactive)
        horizontal.setStretchLastSection(False)
        horizontal.setMinimumSectionSize(60)
        horizontal.sectionResized.connect(self._on_column_resized)

        # 合并多次请求，延后到事件循环空闲时统一重算行高。
        self._pending_heights = QTimer(self)
        self._pending_heights.setSingleShot(True)
        self._pending_heights.setInterval(0)
        self._pending_heights.timeout.connect(self._apply_pending_heights)
        self._resize_all = False
        self._pending_rows: set[int] = set()
        self._wrapping_columns: list[int] | None = None

    # ---- 主题 ----
    def set_theme_name(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self.setStyleSheet(theme.build_qss(theme_name))

    # ---- 字体 ----
    def set_font(self, family: str = "", size: int = theme.DEFAULT_FONT_SIZE) -> None:
        """设置表格字体，并**按需**触发一次行高重算（不退回整表 resizeRowsToContents）。

        字体变化会影响每一行的高度，因此这里复用 v4 的行高调度机制
        （``schedule_resize`` → ``_resize_row``，仅测换行列 + 单行早退），
        而不是调用对每格都测换行的 ``resizeRowsToContents()``。
        """

        font = theme.build_font(family, size)
        self.setFont(font)
        self.viewport().setFont(font)
        self.horizontalHeader().setFont(font)
        self.verticalHeader().setFont(font)
        self.schedule_resize()

    # ---- 列配置 ----
    def set_wrapping_columns(self, columns: list[int] | None) -> None:
        """限定需要参与换行行高计算的列（``None`` 表示全部列）。

        仅包含长文本列可减少每行需测量的单元格数量，同时保证长文本列仍按需换行。
        """

        self._wrapping_columns = list(columns) if columns else None

    # ---- 模型事件 ----
    def attach_edit_signal(self) -> None:
        """在 model 设置完成后调用，转发编辑事件。"""

        model = self.model()
        if model is not None:
            model.dataChanged.connect(self._on_data_changed)

    def _on_data_changed(self, top_left, bottom_right, roles=None) -> None:  # noqa: N802
        self._schedule_rows(range(top_left.row(), bottom_right.row() + 1))
        self.cell_edited.emit(top_left.row())

    # ---- 行高调度 ----
    def schedule_resize(self) -> None:
        """请求重算整表行高（用于首次载入）。"""

        self._resize_all = True
        self._pending_heights.start()

    def _schedule_rows(self, rows) -> None:
        self._pending_rows.update(rows)
        self._pending_heights.start()

    def _on_column_resized(self, *_args) -> None:
        # 列宽变化会改变换行高度，需要针对整表重算（用户拖动列宽时才发生）。
        self.schedule_resize()

    def _apply_pending_heights(self) -> None:
        model = self.model()
        if model is None:
            self._resize_all = False
            self._pending_rows.clear()
            return
        if self._resize_all:
            rows = list(range(model.rowCount()))
            self._resize_all = False
            self._pending_rows.clear()
        else:
            rows = sorted(self._pending_rows)
            self._pending_rows.clear()
        metrics = QFontMetrics(self.font())
        for row in rows:
            self._resize_row(row, metrics)

    def _resize_row(self, row: int, metrics: QFontMetrics) -> None:
        model = self.model()
        if model is None or not (0 <= row < model.rowCount()):
            return
        delegate = self._delegate
        padding = delegate.HORIZONTAL_PADDING
        height = delegate.base_height(metrics)
        columns = self._wrapping_columns or range(model.columnCount())
        for column in columns:
            text = model.index(row, column).data(Qt.DisplayRole)
            if not text:
                continue
            if not isinstance(text, str):
                text = str(text)
            width = self.columnWidth(column)
            if metrics.horizontalAdvance(text) <= max(40, width - padding):
                continue  # 单行即可容纳，无需测换行
            candidate = delegate.height_for_metrics(metrics, width, text)
            if candidate > height:
                height = candidate
        if self.rowHeight(row) != height:
            self.setRowHeight(row, height)

    def set_column_widths(self, widths: list[int]) -> None:
        """为前若干列设置初始宽度（之后仍可自由拖动）。"""

        model = self.model()
        count = model.columnCount() if model is not None else len(widths)
        for column, width in enumerate(widths[:count]):
            self.setColumnWidth(column, width)
