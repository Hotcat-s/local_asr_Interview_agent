"""跨组件复用的 Qt 信号容器。

用于在不引入额外耦合的前提下，让各视图/控制器能向主窗口广播状态。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class UiSignals(QObject):
    """UI 全局信号总线。"""

    # 状态栏文本
    status_message = Signal(str)
    # 需要以对话框形式提示的错误
    error_occurred = Signal(str)
