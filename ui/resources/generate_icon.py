"""一次性生成应用图标 PNG（无网络 / 无外部图片或字体依赖）。

用法::

    QT_QPA_PLATFORM=offscreen python -m ui.resources.generate_icon

图标本身在运行时由 :func:`ui.theme.app_icon` 程序化绘制；本脚本把同一套绘制
结果落盘为 ``ui/resources/app_icon.png``（256×256）与 ``app_icon_<size>.png``。
即使 PNG 缺失或损坏，运行时也会回退到程序化绘制（见 ``ui.theme.app_icon``）。
"""

from __future__ import annotations

from pathlib import Path


def generate(out_dir: Path | None = None) -> list[Path]:
    """把多尺寸图标写入 ``out_dir``，返回写出的文件路径列表。"""

    from PySide6.QtGui import QGuiApplication  # noqa: PLC0415

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841

    from ui import theme  # noqa: PLC0415

    target = Path(out_dir) if out_dir is not None else Path(__file__).resolve().parent
    written: list[Path] = []
    for size in theme._ICON_SIZES:
        pixmap = theme._render_icon_pixmap(size)
        name = "app_icon.png" if size == 256 else f"app_icon_{size}.png"
        path = target / name
        if pixmap.save(str(path), "PNG"):
            written.append(path)
    return written


def main() -> int:
    written = generate()
    for path in written:
        print(f"written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
