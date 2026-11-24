"""主窗口：现代化三栏布局，转写与分析分离，无菜单栏 / 无状态栏。

┌──────────────┬───────────────────────────────────────────────┐
│ 录音库        │ 工作区（标题/状态/动作 + 转写/问答/报告）        │
│ (可拖动)      │                                               │
│ [左下: ⚙ 设置]│ 底部：阶段化进度面板（无百分比数字）             │
└──────────────┴───────────────────────────────────────────────┘

唯一导入入口位于左侧录音库面板；设置按钮固定在左下角。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui import theme
from ui.controllers.analysis_controller import AnalysisController
from ui.controllers.library_controller import LibraryController
from ui.controllers.settings_controller import SettingsController
from ui.signals import UiSignals
from ui.views.import_view import AUDIO_FILTER, ImportView
from ui.views.library_panel import LibraryPanel
from ui.views.progress_panel import ProgressPanel
from ui.views.settings_dialog import SettingsDialog
from ui.views.widgets import AccentButton, IconButton, ask_text, confirm, notify
from ui.views.workspace_view import WorkspaceView

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.config import AppConfig
    from core.engine import InterviewEngine
    from core.progress import ProgressEvent

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(
        self,
        config: "AppConfig | None" = None,
        engine: "InterviewEngine | None" = None,
        library: LibraryController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("面试录音复盘工具")
        self.resize(1240, 800)

        self._config = config
        self._theme_name = getattr(config, "theme", "dark") if config is not None else "dark"
        self._font_family = str(getattr(config, "font_family", "") or "") if config is not None else ""
        self._font_size = theme.clamp_font_size(getattr(config, "font_size", theme.DEFAULT_FONT_SIZE)) if config is not None else theme.DEFAULT_FONT_SIZE
        self._current: Any = None  # core.RecordingDetail
        self._transcribing_id: int | None = None
        self._analyzing_id: int | None = None
        self._stage = ""

        # 部分 Linux 桌面环境只认窗口图标（不认应用图标），两边都设置。
        self.setWindowIcon(theme.app_icon())

        # 编辑防抖：避免每次按键都写库 / 弹提示。
        # 只保留最新一次编辑，静默期结束后统一落库。
        self._edit_timer = QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(600)
        self._edit_timer.timeout.connect(self._flush_pending_edits)
        self._dirty_transcript = False
        self._dirty_qa = False

        self._signals = UiSignals(self)

        self._analysis = AnalysisController(engine=engine, parent=self)
        if config is not None:
            self._analysis.set_config(config)

        if library is not None:
            self._library = library
        else:
            db_path = getattr(config, "db_path", "data/interview.db") if config is not None else "data/interview.db"
            self._library = LibraryController(db_path, parent=self)

        self._settings = SettingsController(config, parent=self)

        self._build_ui()
        self._connect_signals()
        self._install_shortcuts()
        self._refresh_library()
        self._apply_font()

    # ------------------------------------------------------------------ 构建

    def _build_ui(self) -> None:
        self._library_panel = LibraryPanel(self._theme_name, self)
        self._settings_button = IconButton("⚙", "设置", 38, self)

        side = QWidget(self)
        side.setObjectName("sidePanel")
        side.setMinimumWidth(220)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        side_layout.addWidget(self._library_panel, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(12, 8, 12, 12)
        bottom_row.addWidget(self._settings_button)
        bottom_row.addStretch(1)
        side_layout.addLayout(bottom_row)

        # 右侧：空状态 / 工作区 + 底部进度面板
        self._import_view = ImportView(self)
        self._workspace = WorkspaceView(self._theme_name, self)
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._import_view)
        self._stack.addWidget(self._workspace)

        self._progress_panel = ProgressPanel(self)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._stack, 1)
        right_layout.addWidget(self._progress_panel)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(side)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 940])
        splitter.setChildrenCollapsible(False)

        central = QWidget(self)
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)
        self._splitter = splitter

    def _connect_signals(self) -> None:
        # 录音库
        self._library_panel.import_requested.connect(self._on_import)
        self._library_panel.open_requested.connect(self._library.open_recording)
        self._library_panel.delete_requested.connect(self._on_delete)
        self._library_panel.rename_requested.connect(self._on_rename)
        self._library_panel.retranscribe_requested.connect(self._on_retranscribe)
        self._library_panel.filter_changed.connect(lambda *_: self._refresh_library())
        self._library.library_changed.connect(self._refresh_library)
        self._library.recording_opened.connect(self._on_recording_opened)
        self._library.error.connect(self._on_error)

        # 导入 / 工作区
        self._import_view.audio_selected.connect(self._import_audio)
        self._workspace.transcribe_requested.connect(self._on_transcribe)
        self._workspace.analyze_requested.connect(self._on_analyze)
        self._workspace.rebuild_qa_requested.connect(self._on_rebuild_qa)
        self._workspace.transcript_edited.connect(self._on_transcript_edited)
        self._workspace.qa_edited.connect(self._on_qa_edited)

        # 分析控制器
        self._analysis.progress.connect(self._on_progress)
        self._analysis.transcribed.connect(self._on_transcribed)
        self._analysis.analyzed.connect(self._on_analyzed)
        self._analysis.error.connect(self._on_error)
        self._analysis.canceled.connect(self._on_canceled)
        self._analysis.busy_changed.connect(self._on_busy_changed)
        self._analysis.stage_changed.connect(self._on_stage_changed)

        # 设置
        self._settings_button.clicked.connect(self._on_open_settings)
        self._settings.config_saved.connect(self._on_config_saved)

    def _install_shortcuts(self) -> None:
        for seq, handler in (
            ("Ctrl+O", self._on_import),
            ("Ctrl+1", lambda: self._workspace.show_tab(0)),
            ("Ctrl+2", lambda: self._workspace.show_tab(1)),
            ("Ctrl+3", lambda: self._workspace.show_tab(2)),
            ("F5", self._on_transcribe),
            ("F6", self._on_analyze),
        ):
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.activated.connect(handler)

    # ------------------------------------------------------------------ 录音库

    def _refresh_library(self) -> None:
        status = self._library_panel.status_filter()
        search = self._library_panel.search_text()
        items = self._library.refresh(status=status, search=search)
        self._library_panel.set_recordings(items)

    def _current_id(self) -> int | None:
        if self._current is None:
            return None
        recording = getattr(self._current, "recording", self._current)
        return int(getattr(recording, "id", 0) or 0) or None

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择音频文件", "", AUDIO_FILTER)
        if path:
            self._import_audio(path)

    def _import_audio(self, path: str) -> None:
        default_title = Path(path).stem or "未命名录音"
        title, ok = ask_text(self, "导入录音", "为这段录音命名：", default_title)
        if not ok:
            return
        title = title or default_title
        try:
            recording_id = self._library.import_audio(path, title)
        except Exception as exc:  # noqa: BLE001
            logger.exception("导入录音失败")
            notify(self, "error", "导入失败", str(exc) or exc.__class__.__name__)
            return
        self._refresh_library()
        self._library_panel.select_recording(recording_id)
        # 单击即打开的绑定会让 select_recording 自动触发 open_requested；
        # 仅当选中失败（例如被筛选条件隐藏）时直接打开，避免重复加载。
        if self._library_panel.current_id() != recording_id:
            self._library.open_recording(recording_id)
        notify(self, "success", "已导入", "请点击「开始转写」进行本地转写。")

    def _on_recording_opened(self, detail: Any) -> None:
        # 切换到另一条录音前，先把未落库的编辑写入上一条录音，避免丢失。
        self._flush_pending_edits()
        self._current = detail
        self._workspace.set_detail(detail)
        self._stack.setCurrentWidget(self._workspace)
        self._progress_panel.reset()

    def _on_delete(self, recording_id: int) -> None:
        if not confirm(self, "删除录音", "确定删除这条录音及其转写与分析结果？此操作不可撤销。"):
            return
        self._library.delete_recording(recording_id)
        if self._current_id() == recording_id:
            self._current = None
            self._workspace.clear()
            self._stack.setCurrentWidget(self._import_view)
        notify(self, "info", "已删除", "录音已从库中移除。")

    def _on_rename(self, recording_id: int) -> None:
        recording = self._library.get_recording(recording_id)
        current = str(getattr(recording, "title", "") or "")
        title, ok = ask_text(self, "重命名录音", "新的名称：", current)
        if not ok or not title.strip():
            return
        self._library.rename_recording(recording_id, title.strip())
        if self._current_id() == recording_id:
            self._workspace.set_title(title.strip())
        self._refresh_library()
        notify(self, "success", "已重命名", title.strip())

    def _on_retranscribe(self, recording_id: int) -> None:
        self._library.open_recording(recording_id)
        recording = self._library.get_recording(recording_id)
        if recording is None:
            return
        self._transcribing_id = recording_id
        self._library.set_status(recording_id, "transcribing")
        self._workspace.set_status("transcribing")
        self._analysis.transcribe(getattr(recording, "audio_path", ""))
        self._stack.setCurrentWidget(self._workspace)

    # ------------------------------------------------------------------ 阶段一：转写

    def _on_transcribe(self) -> None:
        if self._analysis.is_busy():
            return
        if self._current is None:
            notify(self, "info", "提示", "请先在左侧选择一条录音。")
            return
        recording = getattr(self._current, "recording", self._current)
        recording_id = int(getattr(recording, "id", 0) or 0)
        audio_path = str(getattr(recording, "audio_path", "") or "")
        if not audio_path:
            notify(self, "warning", "提示", "该录音没有可用的音频路径。")
            return
        self._transcribing_id = recording_id
        self._library.set_status(recording_id, "transcribing")
        self._workspace.set_status("transcribing")
        self._progress_panel.set_operation("transcribe")
        self._analysis.transcribe(audio_path)

    def _on_transcribed(self, transcript: Any) -> None:
        recording_id = self._transcribing_id
        qa_pairs = self._analysis.build_qa(transcript)
        if recording_id:
            self._library.update_transcript(recording_id, transcript)
            self._library.update_qa_pairs(recording_id, qa_pairs)
            # 仅在成功回调里落终态
            self._library.set_status(recording_id, "transcribed")
            self._library.open_recording(recording_id)
        else:
            self._workspace.set_transcript(transcript)
            self._workspace.set_qa_pairs(qa_pairs)
            self._workspace.set_status("transcribed")
        self._transcribing_id = None
        self._progress_panel.reset()
        notify(self, "success", "转写完成", "可继续编辑文本，或点击「开始分析」进行复盘。")

    # ------------------------------------------------------------------ 阶段二：分析

    def _on_analyze(self) -> None:
        if self._analysis.is_busy():
            return
        if self._current is None:
            notify(self, "info", "提示", "请先选择并转写一条录音。")
            return
        qa_pairs = list(getattr(self._current, "qa_pairs", []) or [])
        if not qa_pairs:
            notify(self, "warning", "提示", "请先完成转写，生成问答对后再分析。")
            return
        recording_id = self._current_id()
        llm_config = getattr(self._config, "llm", None) if self._config is not None else None
        self._analyzing_id = recording_id
        if recording_id:
            self._library.set_status(recording_id, "analyzing")
        self._workspace.set_status("analyzing")
        self._progress_panel.set_operation("analyze")
        self._analysis.analyze(qa_pairs, llm_config)

    def _on_analyzed(self, report: Any) -> None:
        recording_id = self._analyzing_id or self._current_id()
        if recording_id:
            self._library.save_report(recording_id, report)  # 内部 mark_analyzed
            self._library.open_recording(recording_id)
        else:
            self._workspace.set_report(report)
            self._workspace.set_status("analyzed")
        self._analyzing_id = None
        self._progress_panel.reset()
        notify(self, "success", "分析完成", "已生成复盘报告。")

    # ------------------------------------------------------------------ 编辑同步

    def _on_transcript_edited(self, *_args: Any) -> None:
        # 只标记脏数据并重启防抖定时器；真正落库在 _flush_pending_edits。
        self._dirty_transcript = True
        self._edit_timer.start()

    def _on_qa_edited(self, *_args: Any) -> None:
        self._dirty_qa = True
        self._edit_timer.start()

    def _flush_pending_edits(self) -> None:
        """把防抖后的最新编辑一次性落库，并同步内存中的 RecordingDetail。"""

        recording_id = self._current_id()
        if not recording_id:
            self._dirty_transcript = False
            self._dirty_qa = False
            return

        if self._dirty_transcript:
            transcript = self._workspace.transcript()
            if self._current is not None:
                self._current.transcript = transcript
            self._library.update_transcript(recording_id, transcript)
            self._dirty_transcript = False
            notify(self, "warning", "转写已修改", "问答对可能已过期，可点击「重新生成问答对」重算。")

        if self._dirty_qa:
            qa_pairs = self._workspace.qa_pairs()
            if self._current is not None:
                self._current.qa_pairs = qa_pairs
            self._library.update_qa_pairs(recording_id, qa_pairs)
            self._dirty_qa = False

    def _on_rebuild_qa(self) -> None:
        recording_id = self._current_id()
        if not recording_id:
            return
        if not confirm(
            self,
            "重新生成问答对",
            "将依据当前转写文本重建问答对，并覆盖你对问答对的所有手工编辑。是否继续？",
        ):
            return
        transcript = self._workspace.transcript()
        pairs = self._library.rebuild_qa_pairs(recording_id, transcript)
        if self._current is not None:
            self._current.qa_pairs = pairs
        self._workspace.set_qa_pairs(pairs)
        self._workspace.show_qa_tab()
        notify(self, "success", "已重新生成", f"共 {len(pairs)} 个问答对。")

    # ------------------------------------------------------------------ 进度与状态

    def _on_progress(self, event: "ProgressEvent") -> None:
        self._progress_panel.set_event(event)

    def _on_stage_changed(self, stage: str) -> None:
        self._stage = stage
        if stage:
            self._progress_panel.set_operation(stage)
        self._workspace.set_busy(self._analysis.is_busy(), stage)

    def _on_busy_changed(self, busy: bool) -> None:
        self._library_panel.setEnabled(not busy)
        self._settings_button.setEnabled(not busy)
        self._workspace.set_busy(busy, self._stage)

    def _on_error(self, message: str) -> None:
        stage = self._analysis.current_stage()
        failure_id = self._transcribing_id if stage == "transcribe" else self._analyzing_id
        if failure_id:
            self._library.set_status(failure_id, "failed", message)
        self._transcribing_id = None
        self._analyzing_id = None
        self._progress_panel.reset()
        notify(self, "error", "出错了", message, duration=5000)

    def _on_canceled(self) -> None:
        self._transcribing_id = None
        self._analyzing_id = None
        self._progress_panel.reset()
        notify(self, "info", "已取消", "任务已取消。")

    # ------------------------------------------------------------------ 设置

    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        dialog.exec()

    def _on_config_saved(self, config: "AppConfig") -> None:
        self._config = config
        self._analysis.set_config(config)
        self._library.set_db_path(getattr(config, "db_path", "data/interview.db"))
        self._font_family = str(getattr(config, "font_family", self._font_family) or "")
        self._font_size = theme.clamp_font_size(
            getattr(config, "font_size", self._font_size)
        )
        new_theme = getattr(config, "theme", self._theme_name)
        if new_theme != self._theme_name:
            self._apply_theme(new_theme)
        self._apply_font()
        self._refresh_library()
        notify(self, "success", "设置已保存", "配置已更新。")

    def _apply_font(self) -> None:
        """把当前字体设置套用到主要内容区（表格 / 报告 / 进度面板 / 标题）。"""

        self._workspace.set_font(self._font_family, self._font_size)
        self._progress_panel.set_font(self._font_family, self._font_size)

    def _apply_theme(self, theme_name: str) -> None:
        self._theme_name = theme_name
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, theme_name)
        self._library_panel.set_theme_name(theme_name)
        self._workspace.set_theme_name(theme_name)
        self._progress_panel.set_theme_name(theme_name)
        # 主题切换可能重置控件字体，重新套用以免字体设置丢失。
        self._apply_font()

    # ------------------------------------------------------------------ 生命周期

    def closeEvent(self, event) -> None:  # noqa: N802
        # 退出前确保编辑器中的最后一次修改已落库。
        self._flush_pending_edits()
        if self._analysis.is_busy():
            self._analysis.cancel()
        super().closeEvent(event)
