"""工作区：录音标题栏 + 转写/问答/报告三个 tab。

转发子视图的编辑事件，并提供“重新生成问答对”入口（用于转写文本被编辑后，
按用户显式确认重建 Q/A）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import PushButton

from ui import theme
from ui.views.qa_view import QAView
from ui.views.report_view import ReportView
from ui.views.transcript_view import TranscriptView
from ui.views.widgets import AccentButton, StatusBadge

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.schemas import QAPair, Transcript


def _attr(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class WorkspaceView(QWidget):
    """选中录音后展示其内容与操作入口。"""

    transcribe_requested = Signal()
    analyze_requested = Signal()
    rebuild_qa_requested = Signal()
    transcript_edited = Signal()
    qa_edited = Signal()

    def __init__(self, theme_name: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name
        self._status = ""
        self._has_qa = False
        self._busy = False

        self._title = QLabel("", self)
        self._title.setStyleSheet("font-weight: 600;")
        self._badge = StatusBadge("", theme_name, self)

        self._rebuild_button = PushButton("重新生成问答对", self)
        self._rebuild_button.setToolTip("依据当前转写文本重建问答对（会覆盖对问答对的手工编辑）")
        self._transcribe_button = AccentButton("开始转写", self)
        self._analyze_button = AccentButton("开始分析", self)

        header = QHBoxLayout()
        header.setContentsMargins(16, 12, 16, 12)
        header.setSpacing(10)
        header.addWidget(self._title)
        header.addWidget(self._badge)
        header.addStretch(1)
        header.addWidget(self._rebuild_button)
        header.addWidget(self._transcribe_button)
        header.addWidget(self._analyze_button)

        header_container = QWidget(self)
        header_container.setObjectName("headerBar")
        header_container.setLayout(header)

        self._transcript_view = TranscriptView(self, theme_name=theme_name)
        self._qa_view = QAView(self, theme_name=theme_name)
        self._report_view = ReportView(self, theme_name=theme_name)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._transcript_view, "转写文本")
        self._tabs.addTab(self._qa_view, "问答对")
        self._tabs.addTab(self._report_view, "复盘报告")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header_container)
        layout.addWidget(self._tabs, 1)

        self._transcribe_button.clicked.connect(self.transcribe_requested)
        self._analyze_button.clicked.connect(self.analyze_requested)
        self._rebuild_button.clicked.connect(self.rebuild_qa_requested)
        self._transcript_view.transcript_edited.connect(self.transcript_edited)
        self._qa_view.qa_edited.connect(self.qa_edited)

        self.set_font("", theme.DEFAULT_FONT_SIZE)
        self._refresh_actions()

    # ---- 对外 API ----
    def set_detail(self, detail: Any) -> None:
        """填充一条 :class:`core.schemas.RecordingDetail`（或兼容对象）。

        切换录音时先清空三个视图再填充，并把 tab 重置回“转写文本”，
        以免残留上一条录音的视觉内容或停留在旧 tab。
        """

        # 先清空，避免旧数据闪现。
        self._transcript_view.clear()
        self._qa_view.clear()
        self._report_view.clear()

        recording = _attr(detail, "recording", detail)
        title = str(_attr(recording, "title", "") or "未命名录音")
        self._title.setText(title)
        self._status = str(_attr(recording, "status", "") or "")
        self._badge.set_status(self._status)

        self._transcript_view.set_transcript(_attr(detail, "transcript"))
        qa_pairs = _attr(detail, "qa_pairs", []) or []
        self._has_qa = bool(qa_pairs)
        self._qa_view.set_qa_pairs(qa_pairs)
        self._report_view.set_report(_attr(detail, "report"))
        self._tabs.setCurrentIndex(0)
        self._refresh_actions()

    def set_status(self, status: str) -> None:
        self._status = status or ""
        self._badge.set_status(self._status)
        self._refresh_actions()

    def set_title(self, title: str) -> None:
        self._title.setText(title or "未命名录音")

    def set_transcript(self, transcript: "Transcript | None") -> None:
        self._transcript_view.set_transcript(transcript)

    def set_qa_pairs(self, qa_pairs: "list[QAPair] | None") -> None:
        self._has_qa = bool(qa_pairs)
        self._qa_view.set_qa_pairs(qa_pairs)
        self._refresh_actions()

    def set_report(self, report: Any) -> None:
        self._report_view.set_report(report)
        if report is not None:
            self._tabs.setCurrentWidget(self._report_view)

    def transcript(self) -> "Transcript":
        return self._transcript_view.transcript()

    def qa_pairs(self) -> "list[QAPair]":
        return self._qa_view.qa_pairs()

    def show_qa_tab(self) -> None:
        self._tabs.setCurrentWidget(self._qa_view)

    def show_tab(self, index: int) -> None:
        if 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)

    def set_busy(self, busy: bool, stage: str = "") -> None:
        self._busy = busy
        self._refresh_actions()
        self._transcribe_button.setText("转写中…" if busy and stage == "transcribe" else "开始转写")
        self._analyze_button.setText("分析中…" if busy and stage == "analyze" else "开始分析")

    def set_theme_name(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self._badge.set_theme_name(theme_name)
        self._transcript_view.set_theme_name(theme_name)
        self._qa_view.set_theme_name(theme_name)
        self._report_view.set_theme_name(theme_name)

    def set_font(self, family: str = "", size: int = theme.DEFAULT_FONT_SIZE) -> None:
        """套用主要内容区字体（标题 + 转写/问答/报告子视图）。"""

        clamped = theme.clamp_font_size(size)
        title_font = theme.build_font(family, clamped)
        title_font.setPointSize(min(theme.FONT_SIZE_MAX + 6, clamped + 3))
        title_font.setBold(True)
        self._title.setFont(title_font)
        self._transcript_view.set_font(family, clamped)
        self._qa_view.set_font(family, clamped)
        self._report_view.set_font(family, clamped)

    def clear(self) -> None:
        self._title.setText("")
        self._status = ""
        self._has_qa = False
        self._badge.set_status("")
        self._transcript_view.clear()
        self._qa_view.clear()
        self._report_view.clear()
        self._tabs.setCurrentIndex(0)
        self._refresh_actions()

    # ---- 内部 ----
    def _refresh_actions(self) -> None:
        busy = self._busy
        has_recording = bool(self._title.text())
        self._transcribe_button.setEnabled(has_recording and not busy)

        analyzable = self._status in {"transcribed", "analyzed"} and self._has_qa
        self._analyze_button.setEnabled(analyzable and not busy)
        if not analyzable:
            self._analyze_button.setToolTip("请先完成转写")
        elif busy:
            self._analyze_button.setToolTip("有任务正在运行")
        else:
            self._analyze_button.setToolTip("对已转写的问答对进行大模型分析")

        self._rebuild_button.setEnabled(has_recording and not busy)
