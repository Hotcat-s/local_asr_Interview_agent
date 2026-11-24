"""可复用的小组件与交互辅助：状态徽章、卡片、按钮、空状态、输入/提示。

这些组件只负责视觉呈现与轻量交互，配色/文案统一从 :mod:`ui.theme` 获取。
外观优先使用 :mod:`qfluentwidgets` 组件，保持现代观感。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
)

from ui import theme


class StatusBadge(QLabel):
    """以圆角胶囊展示录音状态的小徽章。"""

    def __init__(self, status: str = "", theme_name: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name
        self._status = ""
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_status(status)

    def set_theme_name(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self.set_status(self._status)

    def status(self) -> str:
        return self._status

    def set_status(self, status: str) -> None:
        self._status = status or ""
        color = theme.status_color(status, self._theme_name)
        self.setText(theme.status_label(status))
        self.setStyleSheet(
            f"color: {color};"
            f"border: 1px solid {color};"
            "border-radius: 9px;"
            "padding: 2px 10px;"
            "font-size: 12px;"
            "font-weight: 600;"
        )


class Card(CardWidget):
    """带圆角描边的卡片容器（基于 qfluentwidgets 的 CardWidget）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(8)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class IconButton(PushButton):
    """圆形图标按钮（用于左下角设置等入口）。"""

    def __init__(
        self,
        glyph: str,
        tooltip: str = "",
        diameter: int = 36,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setText(glyph)
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        radius = diameter // 2
        self.setStyleSheet(f"PushButton {{ border-radius: {radius}px; font-size: 16px; }}")
        if tooltip:
            self.setToolTip(tooltip)


class AccentButton(PrimaryPushButton):
    """主操作按钮（accent 高亮，基于 qfluentwidgets）。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)


class SectionTitle(BodyLabel):
    """小号分组标题。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setStyleSheet("font-weight: 600;")


class EmptyState(QWidget):
    """居中的空状态占位：大图标 + 标题 + 说明 + 可选动作按钮。"""

    def __init__(
        self,
        glyph: str,
        title: str,
        subtitle: str = "",
        action_text: str = "",
        on_action: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        glyph_label = QLabel(glyph, self)
        glyph_label.setAlignment(Qt.AlignCenter)
        glyph_label.setStyleSheet("font-size: 56px;")

        title_label = QLabel(title, self)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 17px; font-weight: 600;")

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(glyph_label)
        layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle, self)
            sub.setObjectName("muted")
            sub.setWordWrap(True)
            sub.setAlignment(Qt.AlignCenter)
            layout.addWidget(sub)
        if action_text:
            button = AccentButton(action_text, self)
            if on_action is not None:
                button.clicked.connect(on_action)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(button)
            row.addStretch(1)
            layout.addSpacing(8)
            layout.addLayout(row)
        layout.addStretch(1)


# --------------------------------------------------------------------------- 交互辅助


class TextInputDialog(QDialog):
    """轻量文本输入对话框（导入命名 / 重命名共用）。"""

    def __init__(
        self,
        title: str,
        label: str,
        default: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)

        caption = BodyLabel(label, self)
        self._edit = LineEdit(self)
        self._edit.setText(default)
        self._edit.selectAll()

        ok_button = PrimaryPushButton("确定", self)
        cancel_button = PushButton("取消", self)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(ok_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(caption)
        layout.addWidget(self._edit)
        layout.addSpacing(6)
        layout.addLayout(buttons)

        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        self._edit.returnPressed.connect(self.accept)

    def value(self) -> str:
        return self._edit.text().strip()


def ask_text(
    parent: QWidget | None,
    title: str,
    label: str,
    default: str = "",
) -> tuple[str, bool]:
    """弹出文本输入框，返回 ``(文本, 是否确认)``。"""

    dialog = TextInputDialog(title, label, default, parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.value(), True
    return "", False


def confirm(parent: QWidget | None, title: str, content: str) -> bool:
    """是 / 否确认对话框，返回用户是否点击“是”。"""

    box = MessageBox(title, content, parent)
    box.yesButton.setText("是")
    box.cancelButton.setText("否")
    return bool(box.exec())


def notify(
    parent: QWidget | None,
    kind: str,
    title: str,
    content: str,
    duration: int = 3000,
) -> None:
    """右上角信息提示条（qf InfoBar）。kind ∈ {success, info, warning, error}。"""

    emit = getattr(InfoBar, kind, None) or InfoBar.info
    emit(
        title=title,
        content=content,
        duration=duration,
        position=InfoBarPosition.TOP_RIGHT,
        parent=parent,
    )
