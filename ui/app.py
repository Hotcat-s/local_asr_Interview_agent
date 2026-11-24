"""应用启动引导。"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication


def _load_config():
    """加载 :class:`core.config.AppConfig`，失败时降级为 None。"""

    try:
        from core.config import AppConfig  # noqa: PLC0415

        return AppConfig.load()
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("加载配置失败，将使用默认配置")
        return None


def run(argv: list[str] | None = None) -> int:
    """创建 QApplication 与主窗口，应用主题并进入事件循环。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Local Interview Agent")

    config = _load_config()

    from ui import theme  # noqa: PLC0415

    theme_name = getattr(config, "theme", "dark") if config is not None else "dark"
    theme.apply_theme(app, theme_name)
    app.setWindowIcon(theme.app_icon())

    from ui.main_window import MainWindow  # noqa: PLC0415

    window = MainWindow(config=config)
    window.show()
    return app.exec()
