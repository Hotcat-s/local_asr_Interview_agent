"""现代化主题：颜色常量、状态文案、以及 qfluentwidgets 主题桥接。

本模块只负责“长什么样”，不含任何业务逻辑。视觉基调交由
:mod:`qfluentwidgets` 的 ``setTheme`` 主导；这里只保留：

* 状态徽章用的颜色与中文文案（:func:`status_color` / :func:`status_label`）；
* 供 qfluentwidgets 未覆盖的少量原生控件（表格 / 文本浏览器 / 分割条）使用的
  局部 QSS，避免影响 qf 组件自身的观感。
"""

from __future__ import annotations

import logging
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- 字体

FONT_SIZE_MIN = 9
FONT_SIZE_MAX = 24
DEFAULT_FONT_SIZE = 12

# 跨平台候选项；空字符串代表“使用应用默认字体”。实际可用性由设置界面按系统过滤。
FONT_FAMILY_CANDIDATES: list[str] = [
    "",
    "Microsoft YaHei",
    "微软雅黑",
    "PingFang SC",
    "Source Han Sans SC",
    "Noto Sans CJK SC",
    "SimHei",
    "SimSun",
    "Arial",
    "Consolas",
]

# --------------------------------------------------------------------------- 调色板

COLORS: dict[str, str] = {
    "bg": "#11151c",
    "panel": "#181e27",
    "panel_alt": "#1f2733",
    "border": "#2a3441",
    "text": "#e6edf3",
    "text_muted": "#8b98a9",
    "accent": "#4f8cff",
    "accent_hover": "#6ea0ff",
    "accent_pressed": "#3d76e0",
    "success": "#3fb950",
    "warning": "#d29922",
    "danger": "#f85149",
    "teal": "#2aa6a6",
    "selection": "#243447",
}

LIGHT_COLORS: dict[str, str] = {
    "bg": "#f4f6f9",
    "panel": "#ffffff",
    "panel_alt": "#eef1f5",
    "border": "#d7dde5",
    "text": "#1b2430",
    "text_muted": "#6b7684",
    "accent": "#2f6fed",
    "accent_hover": "#4a83f5",
    "accent_pressed": "#2459c9",
    "success": "#1a7f37",
    "warning": "#9a6700",
    "danger": "#cf222e",
    "teal": "#0f7a7a",
    "selection": "#dfe8fb",
}


def palette(theme: str = "dark") -> dict[str, str]:
    """返回指定主题的调色板。"""

    return LIGHT_COLORS if theme == "light" else COLORS


def clamp_font_size(size: object) -> int:
    """把任意值裁剪到合法字号区间（非法值回退默认）。"""

    try:
        value = int(size)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE
    return max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, value))


def build_font(family: str = "", size: int = DEFAULT_FONT_SIZE) -> "QFont":
    """按字体族 + 字号构造 ``QFont``（空字体族表示沿用应用默认）。"""

    from PySide6.QtGui import QFont  # noqa: PLC0415

    font = QFont()
    clean = (family or "").strip()
    if clean:
        font.setFamily(clean)
    font.setPointSize(clamp_font_size(size))
    return font


def apply_font(
    target: "QApplication | QWidget | None",
    family: str = "",
    size: int = DEFAULT_FONT_SIZE,
) -> None:
    """把字体设置应用到单个控件（或 ``QApplication``）。

    刻意**不**使用 ``setStyleSheet``——那是整体替换，会冲掉 qfluentwidgets 的
    整套主题样式。这里只调用控件级 ``setFont``，安全且不破坏主题。
    """

    if target is None:
        return
    target.setFont(build_font(family, size))


# --------------------------------------------------------------------------- 状态

# 与 core.status.RecordingStatus 的值保持一致；此处保留字面量以便 core 未就绪时
# UI 仍可独立编译与导入。
_STATUS_LABELS: dict[str, str] = {
    "imported": "待转写",
    "transcribing": "转写中",
    "transcribed": "已转写",
    "analyzing": "分析中",
    "analyzed": "已完成",
    "failed": "处理失败",
}

_STATUS_COLOR_KEYS: dict[str, str] = {
    "imported": "text_muted",
    "transcribing": "accent",
    "transcribed": "teal",
    "analyzing": "accent",
    "analyzed": "success",
    "failed": "danger",
}


def status_label(status: str) -> str:
    """把录音状态值转成中文文案（UI 统一文案源）。"""

    return _STATUS_LABELS.get(status, status or "未知")


def status_color(status: str, theme: str = "dark") -> str:
    """返回录音状态徽章的前景色（hex）。"""

    key = _STATUS_COLOR_KEYS.get(status, "text_muted")
    return palette(theme)[key]


# --------------------------------------------------------------------------- QSS

# 仅覆盖 qfluentwidgets 不负责的原生控件（表格 / 文本浏览器 / 分割条）。
# 刻意不写 QWidget / QPushButton / QLineEdit 等通用选择器，以免覆盖 qf 组件样式。
_EXTRA_QSS = Template(
    """
QTableView {
    background-color: $panel;
    alternate-background-color: $panel_alt;
    border: 1px solid $border;
    border-radius: 8px;
    color: $text;
    gridline-color: transparent;
    selection-background-color: $selection;
    selection-color: $text;
}
QTableView::item {
    padding: 4px 8px;
}
QTableView::item:selected {
    background-color: $selection;
}
QHeaderView::section {
    background-color: $panel_alt;
    color: $text_muted;
    border: none;
    border-bottom: 1px solid $border;
    border-right: 1px solid $border;
    padding: 7px 8px;
    font-weight: 600;
}
QHeaderView::section:last {
    border-right: none;
}
QTableCornerButton::section {
    background-color: $panel_alt;
    border: none;
}
QTextBrowser {
    background-color: $panel;
    color: $text;
    border: none;
}
QSplitter::handle {
    background-color: $border;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:hover {
    background-color: $accent;
}
QToolTip {
    background-color: $panel_alt;
    color: $text;
    border: 1px solid $border;
    padding: 4px 8px;
    border-radius: 4px;
}
"""
)


def build_qss(theme: str = "dark") -> str:
    """按主题生成补充 QSS（不覆盖 qfluentwidgets 组件）。"""

    return _EXTRA_QSS.substitute(palette(theme))


def _build_palette(theme: str = "dark"):
    """按主题生成一份 ``QPalette``，供 qf 未接管的原生/自绘控件使用。"""

    from PySide6.QtGui import QColor, QPalette  # noqa: PLC0415

    pal = palette(theme)
    window = QColor(pal["bg"])
    base = QColor(pal["panel"])
    alt = QColor(pal["panel_alt"])
    text = QColor(pal["text"])
    muted = QColor(pal["text_muted"])
    accent = QColor(pal["accent"])
    selection = QColor(pal["selection"])

    qp = QPalette()
    qp.setColor(QPalette.Window, window)
    qp.setColor(QPalette.WindowText, text)
    qp.setColor(QPalette.Base, base)
    qp.setColor(QPalette.AlternateBase, alt)
    qp.setColor(QPalette.Text, text)
    qp.setColor(QPalette.Button, alt)
    qp.setColor(QPalette.ButtonText, text)
    qp.setColor(QPalette.Highlight, selection)
    qp.setColor(QPalette.HighlightedText, text)
    qp.setColor(QPalette.ToolTipBase, alt)
    qp.setColor(QPalette.ToolTipText, text)
    qp.setColor(QPalette.PlaceholderText, muted)
    qp.setColor(QPalette.Link, accent)
    qp.setColor(QPalette.Disabled, QPalette.WindowText, muted)
    qp.setColor(QPalette.Disabled, QPalette.Text, muted)
    qp.setColor(QPalette.Disabled, QPalette.ButtonText, muted)
    return qp


def apply_theme(app: "QApplication", theme: str = "dark") -> None:
    """应用主题：切换 qfluentwidgets 主题并同步原生控件调色板。

    刻意**不**调用 ``app.setStyleSheet()``——那是整体替换，会把 qfluentwidgets
    注入的整套主题样式冲掉（dark 下控件退回浅色调色板，浅底浅字不可见）。
    原生控件（表格 / 文本浏览器等）的配色改由各自视图内部按当前主题局部设置。
    """

    normalised = "light" if theme == "light" else "dark"
    try:
        from qfluentwidgets import Theme, setTheme  # noqa: PLC0415

        setTheme(Theme.LIGHT if normalised == "light" else Theme.DARK)
    except Exception:  # noqa: BLE001 - qf 不可用时退化为基础调色板
        logger.exception("qfluentwidgets 主题切换失败，回退到内置调色板")

    # 仅同步 QPalette（非整体替换样式表），让 qf 未接管的原生控件与普通 QWidget
    # 也随主题切换前景/背景，保证两套主题下文字都可见。
    app.setPalette(_build_palette(normalised))


# --------------------------------------------------------------------------- 应用图标

_RESOURCES_DIR = Path(__file__).resolve().parent / "resources"
_ICON_PNG = _RESOURCES_DIR / "app_icon.png"
_ICON_SIZES: tuple[int, ...] = (16, 32, 64, 128, 256)
_ICON_CACHE: "QIcon | None" = None


def app_icon() -> "QIcon":
    """返回应用图标（带缓存）。

    优先加载 ``ui/resources/`` 下的静态 PNG（``app_icon.png`` 与 ``app_icon_<size>.png``）；
    缺失或加载失败时**回退**到 :func:`_render_icon_pixmap` 的运行时程序化绘制。
    """

    global _ICON_CACHE
    if _ICON_CACHE is not None:
        return _ICON_CACHE

    from PySide6.QtCore import QSize  # noqa: PLC0415
    from PySide6.QtGui import QIcon  # noqa: PLC0415

    icon = QIcon()
    candidates: list[tuple[Path, int]] = [(_ICON_PNG, 256)]
    candidates.extend(
        (_RESOURCES_DIR / f"app_icon_{size}.png", size)
        for size in _ICON_SIZES
        if size != 256
    )
    for path, size in candidates:
        if path.exists():
            try:
                icon.addFile(str(path), QSize(size, size))
            except Exception:  # noqa: BLE001 - 文件损坏时忽略该尺寸
                logger.exception("加载应用图标 %s 失败", path)

    if icon.isNull() or icon.pixmap(256, 256).isNull():
        icon = QIcon()
        for size in _ICON_SIZES:
            icon.addPixmap(_render_icon_pixmap(size))

    _ICON_CACHE = icon
    return icon


def _render_icon_pixmap(size: int) -> "QPixmap":
    """程序化绘制一枚矢量风格图标：圆角方形底 + 中央麦克风。"""

    from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: PLC0415
    from PySide6.QtGui import (  # noqa: PLC0415
        QColor,
        QLinearGradient,
        QPainter,
        QPen,
        QPixmap,
    )

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        pal = palette("dark")

        # 圆角方形底：accent 渐变
        margin = size * 0.06
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
        radius = size * 0.22
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(pal["accent_hover"]))
        gradient.setColorAt(1.0, QColor(pal["accent_pressed"]))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        # 中央麦克风（白色）
        cx = size / 2.0
        body_w = size * 0.24
        body_h = size * 0.34
        body_top = size * 0.22
        body = QRectF(cx - body_w / 2.0, body_top, body_w, body_h)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(body, body_w / 2.0, body_w / 2.0)

        pen = QPen(QColor("#ffffff"), max(1.5, size * 0.055))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        arc_rect = QRectF(
            cx - size * 0.19,
            body_top + body_h * 0.30,
            size * 0.38,
            size * 0.38,
        )
        painter.drawArc(arc_rect, 180 * 16, 180 * 16)
        painter.drawLine(QPointF(cx, arc_rect.bottom()), QPointF(cx, size * 0.78))
        painter.drawLine(
            QPointF(cx - size * 0.11, size * 0.78),
            QPointF(cx + size * 0.11, size * 0.78),
        )
    finally:
        painter.end()
    return pixmap
