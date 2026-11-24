"""设置对话框：LLM / 分析 / 模型配置，支持连接测试（基于 qfluentwidgets）。"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import BodyLabel, ComboBox, EditableComboBox, LineEdit, PrimaryPushButton, PushButton

from ui import theme
from ui.views.widgets import SectionTitle, notify

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from core.config import AnalysisConfig, AppConfig, LLMConfig, ModelConfig

    from ui.controllers.settings_controller import SettingsController

_FONT_FAMILY_DEFAULT_LABEL = "系统默认"


def _font_family_options() -> list[str]:
    """返回字体族候选项。

    优先列出当前系统确实可用的候选字体；若系统一个候选都没有（如最小化
    环境），则回退为完整候选列表，避免下拉框只剩“系统默认”一项。下拉框可
    编辑，用户仍可手动输入任意字体族。
    """

    from PySide6.QtGui import QFontDatabase  # noqa: PLC0415

    try:
        available = set(QFontDatabase.families())
    except Exception:  # noqa: BLE001 - 字体枚举不可用时列出全部候选
        available = set()
    candidates = [name for name in theme.FONT_FAMILY_CANDIDATES if name]
    present = [name for name in candidates if name in available]
    return [_FONT_FAMILY_DEFAULT_LABEL, *(present or candidates)]


class SettingsDialog(QDialog):
    """编辑 OpenAI 兼容 / 本地 LLM、分块分析与模型配置。"""

    def __init__(self, controller: "SettingsController", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)

        config = controller.config()

        # ---- LLM ----
        self._provider_combo = ComboBox(self)
        self._provider_combo.addItems(["openai", "local"])
        self._base_url_edit = LineEdit(self)
        self._api_key_edit = LineEdit(self)
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._model_edit = LineEdit(self)
        self._temperature_spin = QDoubleSpinBox(self)
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setSingleStep(0.1)
        self._max_tokens_spin = QSpinBox(self)
        self._max_tokens_spin.setRange(64, 32768)
        self._max_tokens_spin.setSingleStep(256)

        # ---- 分块分析 ----
        self._batch_size_spin = QSpinBox(self)
        self._batch_size_spin.setRange(1, 50)
        self._batch_size_spin.setToolTip("每次大模型调用合并分析的问答对数量，越大越省调用但上下文更杂")
        self._max_chars_spin = QSpinBox(self)
        self._max_chars_spin.setRange(500, 100000)
        self._max_chars_spin.setSingleStep(500)
        self._summary_combo = ComboBox(self)
        self._summary_combo.addItems(["启用", "关闭"])

        # ---- 模型 / 外观 ----
        self._device_combo = ComboBox(self)
        self._device_combo.addItems(["cuda", "cpu"])
        self._theme_combo = ComboBox(self)
        self._theme_combo.addItems(["dark", "light"])

        # ---- 字体 / 外观 ----
        self._font_family_combo = EditableComboBox(self)
        self._font_family_combo.addItems(_font_family_options())
        self._font_family_combo.setToolTip("可选择或直接输入字体族名称；「系统默认」表示沿用应用默认字体")
        self._font_size_spin = QSpinBox(self)
        self._font_size_spin.setRange(theme.FONT_SIZE_MIN, theme.FONT_SIZE_MAX)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setToolTip("主要内容区（表格 / 报告 / 进度文本）基础字号")
        self._preview = BodyLabel("预览：本地面试复盘工具 AaBb 123", self)

        form = QFormLayout()
        form.addRow("提供方：", self._provider_combo)
        form.addRow("Base URL：", self._base_url_edit)
        form.addRow("API Key：", self._api_key_edit)
        form.addRow("模型名称：", self._model_edit)
        form.addRow("Temperature：", self._temperature_spin)
        form.addRow("Max Tokens：", self._max_tokens_spin)
        form.addRow("每批问答对数：", self._batch_size_spin)
        form.addRow("单批字符上限：", self._max_chars_spin)
        form.addRow("整体总结：", self._summary_combo)
        form.addRow("本地推理设备：", self._device_combo)
        form.addRow("界面主题：", self._theme_combo)
        form.addRow(SectionTitle("字体 / 外观", self))
        form.addRow("字体族：", self._font_family_combo)
        form.addRow("字号：", self._font_size_spin)
        form.addRow("预览：", self._preview)

        self._test_button = PushButton("测试连接", self)
        self._test_status = BodyLabel("", self)

        save_button = PrimaryPushButton("保存", self)
        cancel_button = PushButton("取消", self)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)

        test_row = QHBoxLayout()
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._test_status, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 18)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addLayout(buttons)

        self._test_button.clicked.connect(self._on_test)
        save_button.clicked.connect(self._on_save)
        cancel_button.clicked.connect(self.reject)
        controller.test_finished.connect(self._on_test_finished)
        self._font_family_combo.currentTextChanged.connect(self._update_font_preview)
        self._font_size_spin.valueChanged.connect(self._update_font_preview)

        self._populate(config)

    # ---- 填充 / 收集 ----
    def _populate(self, config: "AppConfig") -> None:
        llm = config.llm
        index = self._provider_combo.findText(llm.provider)
        self._provider_combo.setCurrentIndex(index if index >= 0 else 0)
        self._base_url_edit.setText(llm.base_url)
        self._api_key_edit.setText(llm.api_key)
        self._model_edit.setText(llm.model)
        self._temperature_spin.setValue(float(llm.temperature))
        self._max_tokens_spin.setValue(int(llm.max_tokens))

        analysis = getattr(config, "analysis", None)
        if analysis is not None:
            self._batch_size_spin.setValue(int(getattr(analysis, "batch_size", 3)))
            self._max_chars_spin.setValue(int(getattr(analysis, "max_chars_per_batch", 8000)))
            self._summary_combo.setCurrentIndex(0 if getattr(analysis, "enable_summary", True) else 1)

        device_index = self._device_combo.findText(config.models.device)
        self._device_combo.setCurrentIndex(device_index if device_index >= 0 else 0)
        theme_index = self._theme_combo.findText(getattr(config, "theme", "dark"))
        self._theme_combo.setCurrentIndex(theme_index if theme_index >= 0 else 0)

        family = str(getattr(config, "font_family", "") or "")
        # 可编辑下拉：用 setText 以便显示/保留不在候选列表中的自定义字体族。
        self._font_family_combo.setText(family or _FONT_FAMILY_DEFAULT_LABEL)
        self._font_size_spin.setValue(
            theme.clamp_font_size(getattr(config, "font_size", theme.DEFAULT_FONT_SIZE))
        )
        self._update_font_preview()

    # ---- 字体 ----
    def _selected_font_family(self) -> str:
        text = self._font_family_combo.currentText().strip()
        if text in ("", _FONT_FAMILY_DEFAULT_LABEL):
            return ""
        return text

    def _update_font_preview(self, *_args: object) -> None:
        theme.apply_font(self._preview, self._selected_font_family(), self._font_size_spin.value())

    def _build_llm_config(self) -> "LLMConfig":
        from core.config import LLMConfig  # noqa: PLC0415

        return LLMConfig(
            provider=self._provider_combo.currentText(),
            base_url=self._base_url_edit.text().strip(),
            api_key=self._api_key_edit.text().strip(),
            model=self._model_edit.text().strip(),
            temperature=float(self._temperature_spin.value()),
            max_tokens=int(self._max_tokens_spin.value()),
        )

    def _build_analysis_config(self) -> "AnalysisConfig":
        from core.config import AnalysisConfig  # noqa: PLC0415

        return AnalysisConfig(
            batch_size=int(self._batch_size_spin.value()),
            max_chars_per_batch=int(self._max_chars_spin.value()),
            enable_summary=self._summary_combo.currentIndex() == 0,
        )

    def _build_model_config(self) -> "ModelConfig":
        base = self._controller.config().models
        return dataclasses.replace(base, device=self._device_combo.currentText())

    # ---- 槽 ----
    def _on_test(self) -> None:
        self._test_button.setEnabled(False)
        self._test_status.setText("测试中…")
        self._controller.test_connection(self._build_llm_config())

    def _on_test_finished(self, ok: bool, message: str) -> None:
        self._test_button.setEnabled(True)
        self._test_status.setText("连接成功" if ok else "连接失败")
        if ok:
            notify(self, "success", "测试连接", f"连接成功：{message}")
        else:
            notify(self, "error", "测试连接", f"连接失败：{message}")

    def _on_save(self) -> None:
        try:
            self._controller.save(
                self._build_llm_config(),
                self._build_model_config(),
                self._build_analysis_config(),
                theme=self._theme_combo.currentText(),
                font_family=self._selected_font_family(),
                font_size=int(self._font_size_spin.value()),
            )
        except Exception as exc:  # noqa: BLE001
            notify(self, "error", "保存失败", str(exc) or exc.__class__.__name__)
            return
        self.accept()
