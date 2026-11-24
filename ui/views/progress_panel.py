"""阶段化进度面板：以步骤条 + 无数字进度条呈现转写 / 分析进度。

按需求：**不显示百分比数字**。用“步骤条（当前阶段高亮）+ 简洁进度条 + 状态文案”
表达运行状态；具体阶段名来自 ``core.progress`` 的 ``STAGE_*`` 常量。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel, ProgressBar

from ui import theme

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.progress import ProgressEvent


def _stage_constants() -> dict[str, str]:
    """从 ``core.progress`` 读取 STAGE_* 常量，失败时回退到契约字面量。"""

    fallback = {
        "STAGE_LOAD": "load",
        "STAGE_MODEL": "model",
        "STAGE_VAD": "vad",
        "STAGE_ASR": "asr",
        "STAGE_DIARIZE": "diarize",
        "STAGE_SEGMENT": "segment",
        "STAGE_QA": "qa",
        "STAGE_LLM": "llm",
        "STAGE_SUMMARY": "summary",
        "STAGE_SAVE": "save",
        "STAGE_DONE": "done",
        "STAGE_ERROR": "error",
    }
    try:
        from core import progress as core_progress  # noqa: PLC0415

        for name in list(fallback):
            fallback[name] = getattr(core_progress, name, fallback[name])
    except Exception:  # noqa: BLE001 - core 未就绪时保持回退
        pass
    return fallback


_STAGE = _stage_constants()

_STAGE_LABELS: dict[str, str] = {
    _STAGE["STAGE_LOAD"]: "读取音频",
    _STAGE["STAGE_MODEL"]: "加载模型",
    _STAGE["STAGE_VAD"]: "语音检测",
    _STAGE["STAGE_ASR"]: "语音识别",
    _STAGE["STAGE_DIARIZE"]: "说话人分离",
    _STAGE["STAGE_SEGMENT"]: "语义分段",
    _STAGE["STAGE_QA"]: "问答配对",
    _STAGE["STAGE_LLM"]: "逐题分析",
    _STAGE["STAGE_SUMMARY"]: "整体总结",
    _STAGE["STAGE_SAVE"]: "保存结果",
    _STAGE["STAGE_DONE"]: "完成",
    _STAGE["STAGE_ERROR"]: "错误",
}


def stage_label(stage: str) -> str:
    """把 core 阶段常量转成中文文案。"""

    return _STAGE_LABELS.get(stage, stage or "")


_TRANSCRIBE_STEPS: list[str] = [
    _STAGE["STAGE_LOAD"],
    _STAGE["STAGE_MODEL"],
    _STAGE["STAGE_ASR"],
    _STAGE["STAGE_QA"],
    _STAGE["STAGE_DONE"],
]
_ANALYZE_STEPS: list[str] = [
    _STAGE["STAGE_LLM"],
    _STAGE["STAGE_SUMMARY"],
    _STAGE["STAGE_DONE"],
]


class ProgressPanel(QWidget):
    """步骤条 + 无数字进度条 + 状态文案。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_name = "dark"
        self._steps: list[str] = list(_TRANSCRIBE_STEPS)
        self._active = -1
        self._font = theme.build_font("", theme.DEFAULT_FONT_SIZE)

        self._status = BodyLabel("就绪", self)
        self._status.setStyleSheet("font-weight: 600;")

        self._steps_row = QHBoxLayout()
        self._steps_row.setContentsMargins(0, 0, 0, 0)
        self._steps_row.setSpacing(6)
        self._step_labels: list[QLabel] = []

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self._status, 1)

        self._bar = ProgressBar(self)
        self._bar.setTextVisible(False)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(4)

        steps_container = QWidget(self)
        steps_container.setLayout(self._steps_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 10)
        layout.setSpacing(6)
        layout.addLayout(top)
        layout.addWidget(steps_container)
        layout.addWidget(self._bar)

        self._rebuild_steps()
        self.reset()

    # ---- 主题 ----
    def set_theme_name(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self._render_steps()

    # ---- 字体 ----
    def set_font(self, family: str = "", size: int = theme.DEFAULT_FONT_SIZE) -> None:
        """设置进度面板文本字体（状态文案 + 步骤标签）。"""

        self._font = theme.build_font(family, size)
        self._status.setFont(self._font)
        for label in self._step_labels:
            label.setFont(self._font)

    # ---- 对外 API ----
    def set_operation(self, operation: str) -> None:
        """按操作类型切换步骤模板：``"transcribe"`` / ``"analyze"``。"""

        steps = _ANALYZE_STEPS if operation == "analyze" else _TRANSCRIBE_STEPS
        if steps != self._steps:
            self._steps = list(steps)
            self._active = -1
            self._rebuild_steps()

    def set_event(self, event: "ProgressEvent") -> None:
        """接收一个 :class:`core.progress.ProgressEvent`。"""

        stage = str(getattr(event, "stage", "") or "")
        message = str(getattr(event, "message", "") or "")
        detail = str(getattr(event, "detail", "") or "")
        percent = float(getattr(event, "percent", 0.0) or 0.0)

        if stage == _STAGE["STAGE_DONE"]:
            self._active = len(self._steps)
        elif stage == _STAGE["STAGE_ERROR"]:
            self._status.setText(message or "处理失败")
            self._bar.setRange(0, 100)
            self._bar.setValue(0)
            return
        elif stage in self._steps:
            self._active = self._steps.index(stage)

        text = message or stage_label(stage) or "处理中"
        if detail:
            text = f"{text} · {detail}"
        self._status.setText(text)

        self._bar.setRange(0, 100)
        self._bar.setValue(int(max(0.0, min(100.0, percent))))
        self._render_steps()

    def reset(self) -> None:
        self._active = -1
        self._status.setText("就绪")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._render_steps()

    def set_indeterminate(self, indeterminate: bool) -> None:
        """忙碌但暂无进度时的循环动画。"""

        if indeterminate:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, 100)

    # ---- 内部 ----
    def _rebuild_steps(self) -> None:
        while self._steps_row.count():
            item = self._steps_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._step_labels = []
        for index, stage in enumerate(self._steps):
            if index:
                arrow = QLabel("›", self)
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setStyleSheet("color: #8b98a9;")
                arrow.setFont(self._font)
                self._steps_row.addWidget(arrow)
            label = QLabel(stage_label(stage), self)
            label.setAlignment(Qt.AlignCenter)
            label.setFont(self._font)
            self._step_labels.append(label)
            self._steps_row.addWidget(label)
        self._steps_row.addStretch(1)
        self._render_steps()

    def _render_steps(self) -> None:
        from ui import theme  # noqa: PLC0415

        pal = theme.palette(self._theme_name)
        for index, label in enumerate(self._step_labels):
            if index < self._active:
                color = pal["success"]
                prefix = "✓ "
            elif index == self._active:
                color = pal["accent"]
                prefix = "● "
            else:
                color = pal["text_muted"]
                prefix = ""
            weight = "600" if index == self._active else "400"
            stage = self._steps[index]
            label.setText(f"{prefix}{stage_label(stage)}")
            label.setStyleSheet(f"color: {color}; font-weight: {weight};")
