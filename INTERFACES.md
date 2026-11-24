# 接口契约 v5（功能增强，Frozen）

> 本文件是 `core` 与 `ui` 并行开发的**唯一标准**。
> v5 是**增量增强**：单击打开、字体设置、应用图标。
> v4 契约已备份为 `INTERFACES_v4_backup.md`（历史参考）。
>
> **写入范围**：core subagent 只允许改 `core/`；ui subagent 只允许改 `ui/`、`main.py`、
> `ui/resources/`（新建资源目录）。两者写入范围**不重叠**。

---

## 0. 本次需求（3 项）

| # | 需求 | 归属 |
|---|---|---|
| 1 | 录音库**左键单击**即打开（现在要双击/右键） | ui |
| 2 | 设置里增加**主要内容区字体大小**与**字体样式（字体族）**配置 | core（配置字段）+ ui（设置界面与生效） |
| 3 | 更换**应用图标** | ui |

---

## 1. 需求 1：单击打开（ui）

**现状（已核实）**：`ui/views/library_panel.py` 只在 `doubleClicked` 上绑定打开；
单击仅 `setCurrentIndex` 选中，不触发 `open_requested`。所以用户要点两下。

**要求**：
- **单击（左键）即打开**该录音。实现方式：把 `open_requested` 的触发从 `doubleClicked`
  改到**选中变化**上，即 `self._view.selectionModel().currentChanged`（或
  `QListView.clicked`）。推荐 `currentChanged`，因为键盘上下键切换也应同步打开。
- 保持**双击仍然可用**（不报错、不重复打开）。注意避免"单击打开 + 双击再打开一次"造成
  重复加载：双击时 `currentChanged` 已先触发过一次，双击回调应**忽略或去重**。
  最简做法：**移除 `doubleClicked` 打开绑定**，只保留 `currentChanged`（双击必然先触发
  currentChanged，因此双击场景天然可用，且不会重复）。
- `select_recording(id)`（程序化选中，如导入后自动打开）不应造成**无限递归**：
  注意 `currentChanged` 会因 `setCurrentIndex` 触发 → 又 emit `open_requested` →
  MainWindow 再 `open_recording`。必须加**去重保护**：若 emit 的 id 与上次已打开的 id
  相同，则跳过（或由 MainWindow 侧去重）。请在实现中明确处理并自测。
- 右键菜单行为不变（仍可打开/重命名/重新转写/删除）。

**验收**：
- 程序化 `setCurrentIndex(另一行)` → 断言 `open_requested` 发出且 id 正确。
- 连续两次选中**同一行** → 只应发出一次（去重），或不产生重复的重复加载。
- `select_recording()` 调用后不出现死循环/递归（可用计数断言或栈深保护）。

---

## 2. 需求 2：字体大小与字体样式设置

### 2.1 core 侧（配置字段）

在 `core/config.py` 的 `AppConfig` 中**新增**两个字段（保持向后兼容，`from_dict` 能容忍缺失）：

```python
font_family: str = ""      # 空字符串 = 使用应用默认字体
font_size: int = 12        # 主要内容区基础字号（pt），合理范围 9-24
```

要求：
- `AppConfig.to_dict/from_dict` 自动支持（当前用 dataclass asdict/_pick 机制，应已自动覆盖；
  请确认并在 `from_dict` 中对 `font_size` 做**范围裁剪**（如 `max(9, min(24, value))`），
  对非法值（非数字）回退默认 12，不抛异常。
- `AppConfig.default()` 使用上述默认值。
- 不引入新依赖。

### 2.2 ui 侧（设置界面 + 生效）

**设置对话框**（`ui/views/settings_dialog.py`）新增一节"字体 / 外观"：
- **字体族下拉框**（可编辑）：推荐填充一组跨平台候选项 + 允许手输。
  候选项建议（按当前系统可用性过滤，或用 `QFontDatabase.families()`）：
  `系统默认(空)`、`Microsoft YaHei`、`微软雅黑`、`PingFang SC`、`Source Han Sans SC`、
  `Noto Sans CJK SC`、`SimHei`、`SimSun`、`Arial`、`Consolas`。
- **字号控件**：`QSpinBox`，范围 9-24，后缀可用 " pt"。
- 建议加**实时预览**：修改后对话框内的示例文本立即变化（可选，但推荐）。
- 保存时通过 `SettingsController.save(..., font_family=..., font_size=...)` 落库到 `AppConfig`。

**生效范围（"主要内容区"）**：至少覆盖
- 转写文本表格（`TranscriptView`）
- 问答对表格（`QAView`）
- 复盘报告（`ReportView` 的 QTextBrowser）
- 进度面板文本、工作区标题等主要内容文本

**生效方式（重要，勿破坏 qf 主题）**：
- **禁止**用 `app.setStyleSheet()` 注入字体（v4 已确认这会冲掉 qfluentwidgets 的整套主题样式）。
- 正确做法（任选，推荐组合）：
  1. **对具体表格/控件**设置字体：`table.setFont(QFont(family, size))`，并同步更新
     表头字体与 `ui/views/table.py` 中用于**行高测量**的 `QFontMetrics`
     （否则字号变大后行高不够、文字会被裁切——这是必须处理的点）。
  2. `ReportView` 在生成的 HTML 里加 `font-family`/`font-size`（HTML 是它自己的内容，安全）。
  3. 主题切换后（`apply_theme`）要**重新套用**字体设置，避免被重置。
- 由于 `ui/views/table.py` 用 `option.font` / `self.font()` 计算换行高度，
  **设置字体后必须触发一次行高重算**，且该重算要走 v4 的**按需**路径（避免又变回
  O(n) 卡顿）。请自测 200 段数据下设置字号后仍不卡。

**接口**：`ui/theme.py` 建议新增
```python
def apply_font(app_or_widget, family: str, size: int) -> None: ...
def build_font(family: str, size: int) -> QFont: ...
```
并在 `MainWindow` 应用配置时调用；`MainWindow._on_config_saved` 收到新配置后立即重套字体。

**验收**：
- 设置 `font_size=20` 后：表格 `font().pointSize()` == 20，且长文本行高相应变大、
  文字完整可见（不被裁切）。
- 设置 `font_family` 为某可用字体后：控件 `font().family()` 生效。
- 保存 → 重新读取 `AppConfig` → 字体设置持久化。
- 切换主题（dark↔light）后字体设置**不丢失**。
- 200 段数据下应用字体耗时合理（不出现明显卡顿，参考 v4 修复后的量级）。

---

## 3. 需求 3：更换应用图标（ui）

**现状**：全项目**没有任何** `setWindowIcon` / `QIcon` / 资源目录。

**要求**：
- 新建 `ui/resources/` 目录，放置一个应用图标文件。
- **图标生成方式（无网络、无新依赖）**：用 PySide6 的 `QPainter` 在代码中**程序化绘制**
  一个矢量风格图标，并保存为 PNG 到 `ui/resources/app_icon.png`（可写一个一次性生成脚本，
  或直接在 `ui/resources/__init__.py` / `ui/theme.py` 里提供 `app_icon() -> QIcon` 函数，
  运行时用 QPainter 生成 QPixmap，避免二进制资源入库问题）。
  - 建议同时输出多尺寸（16/32/64/128/256）或至少 256×256，保证任务栏清晰。
  - 设计：简洁现代，例如圆角方形底色（用 `theme` 的 accent 色）+ 中央符号
    （如麦克风 / 对话气泡 / 声波）。**不要**引入外部图片或字体文件依赖。
- 在 `ui/app.py` 中 `app.setWindowIcon(...)`，并在 `MainWindow.__init__` 里
  `self.setWindowIcon(...)`（部分 Linux 桌面环境只认窗口图标）。
- 提供 `ui/theme.py::app_icon() -> "QIcon"`（或放在 `ui/resources/__init__.py`），
  带**缓存**（避免重复绘制），并在 qf 主题色变化时仍清晰可见。
- 若生成静态 PNG：请把生成脚本保留在 `ui/resources/generate_icon.py`，
  并确保**即使 PNG 缺失也能运行时回退到程序化绘制**（健壮性）。

**验收**：
- `app_icon()` 返回非空 `QIcon`，`pixmap(256,256)` 非空。
- `MainWindow.windowIcon().isNull()` 为 False。
- `app.windowIcon().isNull()` 为 False（ui/app.py 已设置）。
- offscreen 下不报错。

---

## 4. 验证要求

### core（subagent 必须执行）
- `cd /home/qiuqiu/local_Interview_agent && .venv/bin/python -m compileall -q core`
- `cd /home/qiuqiu/local_Interview_agent && .venv/bin/python -m unittest discover -s core/tests`
  —— **当前基线 97 tests，不得回归**，并**新增**字体字段相关测试：
  - 默认值正确（font_family=""、font_size=12）
  - `to_dict`/`from_dict` 往返保持
  - 非法 `font_size`（字符串、负数、超大）被裁剪/回退，不抛异常
  - **旧 config.json（无字体字段）仍能正常加载**（向后兼容）
- core **不得** import PySide6/PyQt/qfluentwidgets；不加载大模型。

### ui（subagent 必须执行）
- `cd /home/qiuqiu/local_Interview_agent && .venv/bin/python -m compileall -q ui main.py`
- `QT_QPA_PLATFORM=offscreen uv run python -c "import ui.main_window, ui.theme; print('ok')"`
- offscreen 自测（假 engine / 临时 DB）：
  1. **单击打开**：`setCurrentIndex` 后 `open_requested` 发出正确 id；同一行重复选中不重复发出。
  2. **字体**：设置 font_size=20 与某字体后，断言表格 `font()` 生效、行高随之增大且
     长文本完整显示；`AppConfig` 持久化；主题切换后字体不丢。
  3. **图标**：`app_icon()` 非空、`pixmap(256,256)` 非空、窗口与 app 图标均非 null。
  4. **不回归**：v3/v4 特性（可编辑表格、三处同步、重命名、单一导入入口、
     无 menuBar/statusBar、无百分比数字、dark 主题可见、右键菜单可用、渲染不卡）保持不变。

---

## 5. 编码规范（沿用）

- Python 3.11，类型注解齐全，`from __future__ import annotations`。
- core 禁止 `PySide6`/`PyQt`/`qfluentwidgets`；`funasr`/`torch` 懒加载。
- 日志用 `logging`，禁止 `print` 作为业务输出。
- **不得破坏 qfluentwidgets 主题**：禁止 `app.setStyleSheet()` 注入全局样式（v4 教训）。
- 向后兼容：v4 公开 API 签名不得删改，v5 只做增量。
- 针对根因实现，不要用 sleep/强制重绘等绕过手法。
