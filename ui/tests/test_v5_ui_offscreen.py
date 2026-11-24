"""v5 UI 自测（offscreen，无模型 / 无网络）。

覆盖 v5 三项增强与 v3/v4 回归项。运行::

    cd /home/qiuqiu/local_Interview_agent
    QT_QPA_PLATFORM=offscreen .venv/bin/python -m ui.tests.test_v5_ui_offscreen

退出码 0 表示全部通过；非 0 表示存在失败项（同时打印失败清单）。
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path


def run() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QEventLoop, Qt
    from PySide6.QtGui import QFontDatabase, QFontMetrics, QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import (
        QApplication,
        QMenuBar,
        QPushButton,
        QStatusBar,
    )

    from core.config import AppConfig, LLMConfig
    from core.schemas import Transcript, TranscriptSegment
    from core.storage.repository import Repository
    from ui import theme
    from ui.controllers.settings_controller import SettingsController
    from ui.main_window import MainWindow
    from ui.models.transcript_model import TranscriptTableModel
    from ui.views.library_panel import LibraryPanel
    from ui.views.table import EditableTableView

    app = QApplication.instance() or QApplication([])

    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: object, detail: object = "") -> None:
        ok = bool(cond)
        results.append((name, ok, str(detail)))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} :: {detail}")

    def pump(times: int = 8) -> None:
        for _ in range(times):
            app.processEvents(QEventLoop.AllEvents, 50)

    def fake_items() -> list[dict]:
        return [
            {"id": 1, "title": "一", "status": "imported", "duration": 10.0, "created_at": ""},
            {"id": 2, "title": "二", "status": "transcribed", "duration": 20.0, "created_at": ""},
            {"id": 3, "title": "三", "status": "analyzed", "duration": 30.0, "created_at": ""},
        ]

    print("\n=== 需求 1：单击打开 ===")
    panel = LibraryPanel("dark")
    panel.set_recordings(fake_items())
    emitted: list[int] = []
    panel.open_requested.connect(emitted.append)

    panel._view.setCurrentIndex(panel._model.index(1))
    check("单击选中行 -> 发出正确 id", emitted == [2], emitted)
    panel._view.setCurrentIndex(panel._model.index(1))
    check("重复选中同一行 -> 不重复发出", emitted == [2], emitted)
    panel._view.setCurrentIndex(panel._model.index(0))
    check("选中另一行 -> 发出新 id", emitted == [2, 1], emitted)

    before = len(emitted)
    panel._view.doubleClicked.emit(panel._model.index(1))
    check("双击不再额外触发打开", len(emitted) == before, emitted)

    panel3 = LibraryPanel("dark")
    panel3.set_recordings(fake_items())
    em3: list[int] = []
    panel3.open_requested.connect(em3.append)
    panel3.select_recording(3)
    check("select_recording 触发 open_requested", em3 == [3], em3)

    panel2 = LibraryPanel("dark")
    panel2.set_recordings(fake_items())
    counter = {"n": 0}

    def naive_handler(rid: int) -> None:
        counter["n"] += 1
        if counter["n"] < 100:
            panel2.select_recording(rid)

    panel2.open_requested.connect(naive_handler)
    panel2.select_recording(2)
    check("select_recording 无递归（计数==1）", counter["n"] == 1, counter["n"])

    print("\n=== 需求 2：字体设置 ===")
    model = QStandardItemModel(3, 3)
    for r in range(3):
        for c in range(3):
            model.setItem(r, c, QStandardItem(f"单元格 {r}-{c}"))
    table = EditableTableView()
    table.setModel(model)
    table.set_column_widths([80, 80, 220])
    table.set_wrapping_columns([2])
    table.resize(600, 400)

    table.set_font("", 20)
    pump()
    check("表格 font().pointSize() == 20", table.font().pointSize() == 20, table.font().pointSize())

    long_text = "这是一段用于测试换行的很长的面试回答文本。" * 12
    model.setItem(0, 2, QStandardItem(long_text))
    table.schedule_resize()
    pump()
    needed = table._delegate.height_for_metrics(
        QFontMetrics(table.font()), table.columnWidth(2), long_text
    )
    h20 = table.rowHeight(0)
    check("大字号长文本行高不裁切", h20 >= needed, f"row={h20} needed={needed}")

    table.set_font("", theme.DEFAULT_FONT_SIZE)
    pump()
    h12 = table.rowHeight(0)
    check("行高随字号增大", h20 > h12, f"h20={h20} h12={h12}")

    families = QFontDatabase.families()
    target_family = "DejaVu Sans" if "DejaVu Sans" in families else (families[0] if families else "Sans Serif")
    table.set_font(target_family, 14)
    pump()
    check("字体族生效", table.font().family() == target_family, table.font().family())

    table.set_font("", 20)
    pump()
    table.set_theme_name("light")
    check("主题切换后表格字体不丢", table.font().pointSize() == 20, table.font().pointSize())

    core_has_font_fields = hasattr(AppConfig, "font_family") and hasattr(AppConfig, "font_size")
    print(f"  core font fields present: {core_has_font_fields}")
    tmpdir = tempfile.mkdtemp()
    cfg = AppConfig()
    cfg.config_path = os.path.join(tmpdir, "config.json")
    sc = SettingsController(cfg)
    sc.save(LLMConfig(), font_family=target_family, font_size=20)
    reloaded = AppConfig.load(cfg.config_path)
    if core_has_font_fields:
        check(
            "font_family 持久化",
            getattr(reloaded, "font_family", "") == target_family,
            getattr(reloaded, "font_family", "<missing>"),
        )
        check(
            "font_size 持久化",
            getattr(reloaded, "font_size", None) == 20,
            getattr(reloaded, "font_size", "<missing>"),
        )
    else:
        check("内存配置写入 font_size（core 缺字段时降级）", getattr(cfg, "font_size", None) == 20)

    model200 = QStandardItemModel(200, 3)
    for r in range(200):
        model200.setItem(r, 0, QStandardItem(f"{r // 60:02d}:{r % 60:02d}"))
        model200.setItem(r, 1, QStandardItem("说话人"))
        model200.setItem(r, 2, QStandardItem(f"第 {r} 段面试回答。" + "内容" * (r % 15)))
    table200 = EditableTableView()
    table200.setModel(model200)
    table200.set_column_widths([80, 80, 640])
    table200.set_wrapping_columns([2])
    table200.resize(900, 600)
    pump()
    table200.set_font("", 12)
    pump()
    start = time.perf_counter()
    table200.set_font("", 20)
    pump()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    check("200 段应用字体耗时 < 300ms", elapsed_ms < 300, f"{elapsed_ms:.1f} ms")

    print("\n=== 需求 3：应用图标 ===")
    icon = theme.app_icon()
    check("app_icon() 非空", not icon.isNull(), icon)
    check("pixmap(256,256) 非空", not icon.pixmap(256, 256).isNull(), icon.pixmap(256, 256).size())

    saved_dir, saved_png, saved_cache = theme._RESOURCES_DIR, theme._ICON_PNG, theme._ICON_CACHE
    theme._RESOURCES_DIR = Path("/nonexistent-dir")
    theme._ICON_PNG = Path("/nonexistent-dir/app_icon.png")
    theme._ICON_CACHE = None
    fallback = theme.app_icon()
    check("PNG 缺失时回退程序化绘制", not fallback.isNull() and not fallback.pixmap(256, 256).isNull())
    theme._RESOURCES_DIR, theme._ICON_PNG, theme._ICON_CACHE = saved_dir, saved_png, saved_cache

    print("\n=== 主窗口集成 + 不回归 ===")
    tmpdir2 = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir2, "t.db")
    repo = Repository(db_path)
    rid = int(repo.create_recording("集成录音", "/tmp/none.mp3"))
    repo.close()

    cfg2 = AppConfig()
    cfg2.db_path = db_path
    cfg2.config_path = os.path.join(tmpdir2, "config.json")
    if core_has_font_fields:
        cfg2.font_family = ""
        cfg2.font_size = 18

    window = MainWindow(config=cfg2)
    pump()

    row = window._library_panel._model.row_of_id(rid)
    window._library_panel._view.setCurrentIndex(window._library_panel._model.index(row))
    pump()
    check("主窗口：单击选中即打开该录音", window._current_id() == rid, window._current_id())

    check("窗口图标非空", not window.windowIcon().isNull())
    app.setWindowIcon(theme.app_icon())
    check("app.windowIcon() 非空", not app.windowIcon().isNull())

    window._font_family = target_family
    window._font_size = 20
    window._apply_font()
    pump()
    t_table = window._workspace._transcript_view._table
    check("MainWindow 字体作用到转写表格", t_table.font().pointSize() == 20, t_table.font().pointSize())
    window._apply_theme("light")
    pump()
    check("主题切换后 MainWindow 字体不丢", t_table.font().pointSize() == 20, t_table.font().pointSize())
    check("apply_theme 未注入全局样式表", app.styleSheet() == "", repr(app.styleSheet()))

    check("无 menuBar", window.findChild(QMenuBar) is None)
    check("无 statusBar", window.findChild(QStatusBar) is None)
    check("ImportView 无导入按钮", len(window._import_view.findChildren(QPushButton)) == 0)

    tv = TranscriptTableModel()
    tv.set_transcript(
        Transcript(segments=[TranscriptSegment(start=0.0, end=1.0, speaker="说话人", text="内容")])
    )
    check("表格开启换行", t_table.wordWrap())
    check("内容列可编辑（model flags）", bool(tv.flags(tv.index(0, 2)) & Qt.ItemIsEditable))
    check("时间列只读（model flags）", not bool(tv.flags(tv.index(0, 0)) & Qt.ItemIsEditable))

    report_browser = window._workspace._report_view._browser
    check("报告浏览器字体生效", report_browser.font().pointSize() == 20, report_browser.font().pointSize())
    check(
        "进度面板字体生效",
        window._progress_panel._status.font().pointSize() == 20,
        window._progress_panel._status.font().pointSize(),
    )

    menu = panel._build_context_menu(7)
    non_sep = [a for a in menu.actions() if not a.isSeparator()]
    check("右键菜单 4 项动作", len(non_sep) == 4, len(non_sep))
    collected: dict[str, list[int]] = {"open": [], "rename": [], "re": [], "del": []}
    panel.open_requested.connect(collected["open"].append)
    panel.rename_requested.connect(collected["rename"].append)
    panel.retranscribe_requested.connect(collected["re"].append)
    panel.delete_requested.connect(collected["del"].append)
    for action in non_sep:
        action.trigger()
    check(
        "右键菜单 4 项信号均可用",
        collected == {"open": [7], "rename": [7], "re": [7], "del": [7]},
        collected,
    )

    bar = window._progress_panel._bar
    check("进度条不显示百分比数字", not bar.isTextVisible(), bar.isTextVisible())

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n=== 汇总：{len(results) - len(failed)}/{len(results)} 通过 ===")
    if failed:
        print("FAILED:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())
