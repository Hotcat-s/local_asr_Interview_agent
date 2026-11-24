"""视图包：纯展示组件，不含业务逻辑。"""

from __future__ import annotations

from ui.views.import_view import ImportView
from ui.views.library_panel import LibraryPanel
from ui.views.progress_panel import ProgressPanel
from ui.views.qa_view import QAView
from ui.views.report_view import ReportView
from ui.views.settings_dialog import SettingsDialog
from ui.views.transcript_view import TranscriptView
from ui.views.workspace_view import WorkspaceView

__all__ = [
    "ImportView",
    "LibraryPanel",
    "ProgressPanel",
    "QAView",
    "ReportView",
    "SettingsDialog",
    "TranscriptView",
    "WorkspaceView",
]
