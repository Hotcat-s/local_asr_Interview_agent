"""导入视图：无录音选中时的空状态引导，支持拖拽音频文件。

按“单一导入入口”要求，此处**不再提供可见的文件选择按钮**——唯一的导入按钮位于
左侧录音库面板（``LibraryPanel``）。本页仅保留拖拽导入与操作指引。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

AUDIO_FILTER = "音频文件 (*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma);;所有文件 (*)"
_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}


class ImportView(QWidget):
    """空状态 / 拖拽导入页。"""

    audio_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        glyph = QLabel("🎧", self)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet("font-size: 64px;")

        title = QLabel("开始你的面试复盘", self)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 600;")

        subtitle = QLabel(
            "点击左侧「导入音频」选择一段面试录音，\n"
            "或直接把音频文件拖到这里。\n\n"
            "导入后先进行本地语音转写（FunASR），\n"
            "转写完成后可再按需触发大模型复盘分析。",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addStretch(2)
        layout.addWidget(glyph)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(subtitle)
        layout.addStretch(3)

    # ---- 拖拽 ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self._first_audio(event.mimeData().urls()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = self._first_audio(event.mimeData().urls())
        if path:
            event.acceptProposedAction()
            self.audio_selected.emit(path)

    @staticmethod
    def _first_audio(urls) -> str:
        for url in urls:
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if Path(path).suffix.lower() in _AUDIO_SUFFIXES:
                return path
        return ""
