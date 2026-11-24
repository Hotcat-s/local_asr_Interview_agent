"""UI 表现层（PySide6）。

仅负责展示与交互，所有业务逻辑通过 ``core`` 提供的 API 完成。
"""

from __future__ import annotations

from ui.app import run

__all__ = ["run"]
