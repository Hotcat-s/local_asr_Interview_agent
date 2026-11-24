# 接口契约 v3（Frozen Interface Contract）

> 本文件是 `core` 与 `ui` 两个子模块并行开发的**唯一契约**，双方必须严格遵守。
> `core` 是**纯 Python 业务逻辑**，禁止 `import PySide6` / `import PyQt` / `qfluentwidgets`。
> `ui` 只做展示与交互，业务逻辑一律调用 `core`。
> 写入范围：core subagent 只允许改 `core/`；ui subagent 只允许改 `ui/` 和 `main.py`。
>
> **v3 变更摘要**：转写文本与问答对**可编辑并三处同步**；录音**重命名**（列表右键 + 导入命名）；
> 移除百分比、弱化进度条、优化状态文案；去掉重复导入入口与底部状态栏；
> UI 迁移到 **qfluentwidgets** 现代化组件。
>
> v2 契约已备份为 `INTERFACES_v2_backup.md`（仅历史参考，勿实现）。

---

## 0. 本次需求与设计决策（务必先读）

### 0.1 需求清单
| # | 需求 | 归属 |
|---|---|---|
| 1 | 转写文本、问答对**可编辑**；编辑后三处同步 | core（持久化）+ ui |
| 2 | 录音**重命名**：列表右键；导入时顶部有命名输入框（可改，默认文件名） | core（已有）+ ui |
| 3 | 去掉百分比；**优化状态文字**（更美观）；删除底部状态栏（与状态重复）；修正转写/问答状态不准 | ui 为主 + core 状态语义 |
| 4 | 去掉重复的导入入口，只保留一个 | ui |
| 5 | 用 **qfluentwidgets** 重建现代化窗口；保留 PySide6 | ui |

### 0.2 关键设计决策

**决策 A：编辑后的数据如何同步（需求 1）**
- `QAView` 编辑"问题/回答"→ **由程序重算**该条的 `answer`/`question` 无需改 index，直接持久化。
- 编辑 `TranscriptView` 的文本 → 会影响 Q/A 对。
  **结论：采用显式重算策略**，不自动静默改数据：
  - 编辑转写文本后，UI 标记为"转写已修改"，并**询问/提供按钮**让用户"重新生成问答对"。
  - 若用户确认重算，core 用 `build_qa()` 依据编辑后的 transcript 重建 Q/A（**这会导致 Q/A 的手工编辑丢失**，必须在 UI 明确警告）。
  - 若用户拒绝，则只保存转写文本，Q/A 保持原样。
- **core 只需保证**：`save_transcript()` 与 `save_qa_pairs()` 能独立覆盖保存；两者都可单独调用。
- 三处同步 = 内存 `RecordingDetail` + 表格视图 + 数据库，由 `LibraryController` 统一收口。

**决策 B：重命名（需求 2）**
- core 已有 `Repository.update_metadata(recording_id, title=...)`，**无需改动**。UI 通过
  `LibraryController.rename_recording()` 调用（新增方法，见 3.4）。
- 导入流程：UI 先弹"命名输入框"（默认 = 文件名去扩展名），确认后才落库。
  用户可改，也可直接确认用默认名。
- 列表右键菜单新增"重命名"，弹输入框。

**决策 C：进度与状态（需求 3）**
- **移除百分比数字**（`ProgressPanel` 不再显示 `xx%` 文本）。
- 进度条：转写/分析期间显示**不确定态（indeterminate 循环）**或按阶段推进的**分阶段进度**，但不显示数字。
  推荐做成"阶段步骤条"（步骤 + 当前阶段高亮 + 简洁进度条）。
- **状态文案优化**：统一由 `theme.status_label()` 提供，要求更自然美观：
  `imported`→"待转写"，`transcribing`→"转写中"，`transcribed`→"已转写"，
  `analyzing`→"分析中"，`analyzed`→"已完成"，`failed`→"处理失败"。
- **删除底部 `statusBar()`**（需求 3）：不再调 `self.statusBar()`。
  运行状态统一由 `ProgressPanel`/`InfoBar` 呈现。
- **修正状态不准**：转写/分析完成后必须把 `status` 精确落到 `transcribed`/`analyzed`；
  失败落 `failed` 且带 `error_message`；只有真正发起分析时才置 `analyzing`。
  core 侧保证 `update_status` 时间戳语义正确，UI 侧保证**只在成功回调里**置终态。

**决策 D：单一导入入口（需求 4）**
- **保留左侧录音库面板内的"导入音频"按钮**（也可用顶部工具栏，二选一，UI 自行决定但**只能有一个可见入口**）。
- 移除 `LibraryPanel.import_requested` 与顶部 `_import_button` 的重复。
  契约规定：**唯一入口在 `LibraryPanel`**，主窗口顶栏不再放"导入音频"按钮。

**决策 E：qfluentwidgets（需求 5）**
- 依赖已装：`PySide6-Fluent-Widgets==1.11.3`（PySide6 6.11.1 保留，qfluentwidgets 构建于其上）。
- **保留 PySide6 作为基础**：`QMainWindow`/`QWidget`/`QAbstractTableModel` 等仍来自 PySide6。
- 用 qfluentwidgets 替换外观组件：按钮、输入框、下拉、列表、对话框、提示条、进度条、图标。
- **窗口形态二选一（UI 自行判断并说明）**：
  - 方案 1（推荐）：`FluentWindow` + `NavigationInterface` 左侧导航（更现代）。
  - 方案 2：保留 `QMainWindow` + 自绘三栏 + qfluentwidgets 控件（改动小）。
  - 二者皆可，但必须满足：无 `menuBar`、无 `statusBar`、单一导入入口、设置按钮在左下角。
- `ui/theme.py` 仍保留（颜色常量 + `status_label`/`status_color`），但 QSS 交由 qfluentwidgets 的
  `setTheme(Theme.DARK)` 主导；`theme.apply_theme()` 需兼容 qfluentwidgets 主题切换。

---

## 1. 目录结构（v3）

```
main.py                          # 入口，ui 负责
core/
  __init__.py
  exceptions.py
  schemas.py
  status.py
  progress.py
  config.py
  engine.py
  editing.py                     # ★新：编辑相关的纯函数工具（重算/校验/规范化）
  models/{__init__,registry,manager}.py
  audio/{__init__,loader,segmenter}.py
  asr/{__init__,engine}.py
  diarization/{__init__,qa_builder}.py
  embeddings/{__init__,bge}.py
  llm/{__init__,client,prompts,analyzer}.py
  storage/{__init__,database,repository}.py
  tests/…

ui/
  __init__.py
  app.py                         # 启动：qfluentwidgets setTheme + 主窗口
  theme.py                       # 颜色常量 + status_label/status_color + apply_theme（兼容 qf）
  main_window.py                 # 主窗口（无 menuBar / 无 statusBar）
  signals.py
  controllers/
    __init__.py
    analysis_controller.py
    library_controller.py        # 新增 rename_recording / update_transcript / update_qa_pairs
    settings_controller.py
  views/
    __init__.py
    library_panel.py             # 唯一导入入口 + 右键重命名
    import_view.py               # 空状态
    workspace_view.py            # 标题/状态/两个动作按钮 + 三个 tab
    transcript_view.py           # ★可编辑
    qa_view.py                   # ★可编辑
    report_view.py
    progress_panel.py            # ★去百分比，改为阶段步骤 + 无数字进度
    settings_dialog.py
    widgets.py                   # qf 组件封装（StatusBadge/Badge/EmptyState/…）
  models/
    __init__.py
    transcript_model.py          # ★支持 setData/flags 可编辑
    qa_model.py                  # ★支持 setData/flags 可编辑
    library_model.py
  resources/
```

★新/★改 = v3 重点。

---

## 2. `core` 对外 API（v3）

> v2 的 API 全部保留不变，v3 **只新增**以下内容。

### 2.1 `core.editing`（★新，纯函数，便于测试）

```python
from core.schemas import Transcript, TranscriptSegment, QAPair

def update_segment_text(transcript: Transcript, index: int, text: str) -> Transcript:
    """返回被修改后的 transcript 副本（不改原对象），index 为 segments 序号。"""

def update_qa_text(qa_pairs: list[QAPair], index: int, *,
                   question: str | None = None,
                   answer: str | None = None) -> list[QAPair]:
    """返回修改后的 qa_pairs 副本；index 为 QAPair.index 的序号（按列表位置）。"""

def normalize_qa_pairs(qa_pairs: list[QAPair]) -> list[QAPair]:
    """按列表位置重排 index 为 0..n-1，保持其他字段。用于重算/删除后修复序号。"""

def transcript_from_segments(segments: list[TranscriptSegment],
                             duration: float = 0.0,
                             language: str = "zh") -> Transcript:
    """由编辑后的 segments 重建 Transcript，并重算 raw_text（拼接所有非空文本）。"""
```

要求：
- 全部为**纯函数**，输入不被原地修改（返回新对象），便于 UI 做撤销/比较。
- `update_segment_text` 对越界 index 抛 `IndexError`（或返回原副本 + 记录日志，二选一并写明）。
- `transcript_from_segments` 重算 `raw_text = " ".join(text for text in ... if text.strip())`。

### 2.2 `core.storage.Repository`（新增 `update_title` 便捷方法）

```python
def rename_recording(self, recording_id: int, title: str) -> None:
    """更新标题并刷新 updated_at。title 为空时忽略（不写入空标题）。"""
```
> 内部复用已有 `update_metadata(recording_id, title=...)`。这是 UI 重命名的唯一入口。

### 2.3 `core.status`（文案已由 UI 负责，core 不变）
枚举值保持：`imported/transcribing/transcribed/analyzing/analyzed/failed`。
core **不负责中文文案**，中文只在 `ui/theme.py` 定义。

### 2.4 编辑持久化语义（务必遵守）
- `save_transcript(recording_id, transcript)`：**整体覆盖** `segments`，并同步
  `duration/language/raw_text`。调用后应保持 `status` 不变（除非调用方显式改）。
- `save_qa_pairs(recording_id, qa_pairs)`：**整体覆盖**，并更新 `recordings.qa_count`。
- `save_report` 会 `mark_analyzed`（v2 行为，保留）。
- **编辑不应清除报告**：仅当用户显式重算 Q/A 或重新分析时才可能使报告失效，
  由 UI 决定是否提示"报告已过期"，core 不做自动删除。

---

## 3. `ui` 契约（v3）

### 3.1 布局（qfluentwidgets 重建）

要求（无论选 FluentWindow 还是改造 QMainWindow）：
- **无 `QMenuBar`**（不得调用 `self.menuBar()`）。
- **无 `QStatusBar`**（不得调用 `self.statusBar()`）。所有状态用 `ProgressPanel` + `InfoBar` 表达。
- **唯一导入入口**：位于左侧录音库面板（`LibraryPanel`）。主窗口顶栏**不得**再放"导入音频"按钮。
- **设置按钮在左下角**（图标按钮）。
- 三栏/导航结构保留：左侧录音库 + 右侧工作区（标题/状态/动作 + 三个 tab）+ 底部阶段进度面板。
- 可选：使用 `FluentWindow` + `NavigationInterface`（需把录音库作为导航页内容）。

### 3.2 可编辑表格（需求 1，核心）

`TranscriptTableModel` 与 `QATableModel` 需支持编辑：
```python
def flags(self, index) -> Qt.ItemFlags:
    # 文本列返回 Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
    # 序号/时间/说话人列返回只读

def setData(self, index, value, role=Qt.EditRole) -> bool:
    # 写回内存模型，emit dataChanged
```
- `TranscriptView`：`setEditTriggers(DoubleClicked | EditKeyPressed | SelectedClicked)`。
  列：时间(只读) / 说话人(只读) / 内容(可编辑)。
- `QAView`：列 序号(只读) / 问题(可编辑) / 回答(可编辑)。
- **文字要完整显示**：
  - `setWordWrap(True)`；
  - **行高随内容自适应**（用 `resizeRowsToContents()`，或自定义 delegate 的 `sizeHint` 计算换行高度）；
  - 垂直表头需可见或至少在 resize 时保证内容不被裁切；
  - 列宽**可自由拖动**（`QHeaderView.Interactive`），且**不要**用 `Stretch` 强制拉伸导致文字被挤没；
  - 允许横向滚动条出现（`setHorizontalScrollMode(ScrollPerPixel)`）；
  - 在窗口/分割条缩放时重新 `resizeRowsToContents()`，保证任何尺寸下文字都可见。
- **编辑后同步（三处）**：cell 编辑 → `itemChanged`/`dataChanged` →
  发出视图信号（`transcript_edited`、`qa_edited`）→ `MainWindow` →
  `LibraryController.update_transcript/update_qa_pairs` 落库 → 内存 `RecordingDetail` 同步。
- **转写文本编辑后的 Q/A 处理**：按决策 A，UI 必须给出明确选择
  （`MessageBox`/`InfoBar` + "重新生成问答对"按钮），不得静默重算、不得静默丢弃。
- 建议加"重新生成问答对"按钮（工作区），调用 `AnalysisController.build_qa()` + 落库 + 刷新。

### 3.3 `ui.controllers.analysis_controller`（v2 保留 + 状态回调）
- 保留 `transcribe()` / `analyze()` / `cancel()` / `build_qa()`。
- 新增（便于 UI 精确置状态）：
  ```python
  def unload_models(self) -> None: ...   # 已有，保留
  def current_stage(self) -> str: ...    # 已有，保留
  ```
- core 的 `ProgressEvent` 仍原样透传（UI 自行决定不再显示百分比）。

### 3.4 `ui.controllers.library_controller`（★新增方法）

```python
class LibraryController(QObject):
    library_changed = Signal()
    recording_opened = Signal(object)      # core.RecordingDetail
    error = Signal(str)

    def __init__(self, db_path: str = "data/interview.db", parent=None): ...
    def set_db_path(self, path: str) -> None: ...
    def refresh(self, status=None, search=None) -> list: ...
    def get_recording(self, recording_id: int): ...
    def counts(self) -> dict: ...
    def import_audio(self, audio_path: str, title: str = "") -> int: ...
    def open_recording(self, recording_id: int) -> None: ...
    def delete_recording(self, recording_id: int) -> None: ...
    def set_status(self, recording_id: int, status: str, error: str = "") -> None: ...
    def save_transcript(self, recording_id: int, transcript) -> None: ...
    def save_qa_pairs(self, recording_id: int, qa_pairs) -> None: ...
    def save_report(self, recording_id: int, report) -> None: ...

    # ---- v3 新增 ----
    def rename_recording(self, recording_id: int, title: str) -> None: ...
    def update_transcript(self, recording_id: int, transcript) -> None:
        """保存编辑后的转写（等价 save_transcript，语义更清晰）。"""
    def update_qa_pairs(self, recording_id: int, qa_pairs) -> None:
        """保存编辑后的问答对（等价 save_qa_pairs）。"""
    def rebuild_qa_pairs(self, recording_id: int, transcript) -> list:
        """用 core.editing + engine.build_qa 依据 transcript 重建 Q/A 并落库，返回新列表。"""
```
> 所有方法失败时发 `error`，不得抛出到 UI 线程外。

### 3.5 `ui.views.library_panel`（★改动）
- **唯一导入入口**：保留 `AccentButton("＋ 导入音频")` 在面板顶部。
- 右键菜单新增：**打开 / 重命名 / 重新转写 / 删除**。
- 新增信号：`rename_requested(int)`。
- 导入流程改为：`import_requested` → 主窗口弹**命名对话框**（默认文件名去扩展名）
  → 用户确认 → `import_audio(path, title)`。
  也允许面板直接发 `(path, title)`；但命名**必须经过用户**，不得默默用文件名落库（除非用户直接确认默认值）。

### 3.6 `ui.views.progress_panel`（★改造，需求 3）
- **不再显示百分比数字**。移除 `_percent` 标签。
- 展示形式：**阶段步骤条**（如：读取音频 → 加载模型 → 语音识别 → 问答配对 → 完成）
  + 当前阶段高亮 + 一条**无数字的进度条**（不确定态或阶段间推进）。
- 状态文字要美观：使用 qfluentwidgets 的 `BodyLabel`/`SubtitleLabel`，字号与颜色统一。
- `reset()` 文案改为"就绪"。
- API 保留：`set_event(event)`、`reset()`、`set_indeterminate(bool)`。
- core 的 `STAGE_*` 仍要用来映射阶段名，不得硬编码字段值。

### 3.7 `ui.theme`（★保留 + 兼容 qf）
```python
COLORS = {...}                       # 保留
DARK/LIGHT 调色板：theme.palette(name) -> dict   # 已有，保留
def build_qss(theme: str = "dark") -> str: ...    # 保留（可精简，qf 主导）
def apply_theme(app, theme: str = "dark") -> None:
    """应用主题：优先使用 qfluentwidgets 的 setTheme(Theme.DARK/LIGHT)，
    同时保留本项目的状态色（status_color/status_label）。"""
def status_color(status: str, theme_name: str = "dark") -> str:
    # imported→灰, transcribing/analyzing→蓝, transcribed→青, analyzed→绿, failed→红
def status_label(status: str) -> str:
    # imported→"待转写", transcribing→"转写中", transcribed→"已转写",
    # analyzing→"分析中", analyzed→"已完成", failed→"处理失败"
```
> `status_label` 的文案是 v3 统一文案源，所有视图（列表徽章、工作区徽章、提示）必须用它。

### 3.8 视图信号汇总（供主窗口连线）
```python
LibraryPanel:    open_requested(int) / delete_requested(int) / rename_requested(int)
                 / retranscribe_requested(int) / import_requested() / filter_changed(str,str)
TranscriptView:  transcript_edited(int)          # 段落序号
QAView:          qa_edited(int)                  # QAPair 列表位置
WorkspaceView:   transcribe_requested() / analyze_requested() / rebuild_qa_requested()
ProgressPanel:   （无信号，纯展示）
```

### 3.9 主窗口职责（v3）
- 无 `menuBar` / 无 `statusBar`。
- 启动：`apply_theme` → 载入配置 → `library.refresh()` → 填充左栏。
- 导入：命名对话框（默认文件名）→ `library.import_audio(path, title)` → 选中 → 打开。
- 重命名：输入对话框 → `library.rename_recording` → 刷新列表 + 工作区标题。
- 编辑同步：`transcript_edited` / `qa_edited` → 落库 → 更新 `self._current`。
- 转写：置 `transcribing` → `transcribe()` → 成功置 `transcribed`（**只在成功回调置终态**），
  失败置 `failed` 并带 error。
- 分析：置 `analyzing` → `analyze()` → 成功 `save_report`（内部 `mark_analyzed`）。
- 重新生成 Q/A：确认对话框（警告会覆盖手工编辑）→ `rebuild_qa_pairs` → 刷新。
- 关闭窗口时若忙 → `cancel()`。

---

## 4. 运行与验证

- 环境：`uv run python main.py`
- 依赖（已装）：funasr 1.3.16、torch 2.5.1+cu124、PySide6 6.11.1、
  **PySide6-Fluent-Widgets 1.11.3**、openai、httpx[socks]、numpy、soundfile、librosa。

### core 验证（必须执行）
- `uv run python -m compileall -q core`
- `uv run python -m unittest discover -s core/tests` —— **全部通过**
- 新增 `core/tests/test_editing.py`：覆盖
  - `update_segment_text`（正常/越界/不改原对象）
  - `update_qa_text`（改问题/改回答/两者/越界）
  - `normalize_qa_pairs`（index 重排）
  - `transcript_from_segments`（raw_text 重算、忽略空白）
  - `Repository.rename_recording`（改名生效、空标题忽略、updated_at 刷新）
  - 编辑后 `save_transcript`/`save_qa_pairs` 覆盖保存且 `qa_count` 同步
- 不得依赖真实音频/GPU/网络；**不要加载大模型**。

### ui 验证（必须执行）
- `uv run python -m compileall -q ui main.py`
- `QT_QPA_PLATFORM=offscreen uv run python -c "import ui.main_window, ui.theme, ui.views.progress_panel, ui.views.transcript_view, ui.views.qa_view, ui.controllers.library_controller; print('ui ok')"`
- offscreen 冒烟（用假 engine / 临时 DB）：
  - (a) **无 menuBar、无 statusBar**（断言 `menuBar().actions()` 为空 / 不创建 statusBar）
  - (b) 导入入口只有一个（`LibraryPanel` 有导入按钮，主窗口顶栏没有）
  - (c) `TranscriptTableModel`/`QATableModel` 的 `flags()` 对文本列含 `ItemIsEditable`；
        `setData()` 成功并发出 `dataChanged`
  - (d) 编辑后触发视图信号；主窗口能落库（检查 DB 中记录已变）
  - (e) `rename_recording` 后列表/工作区标题更新
  - (f) `ProgressPanel` 无百分比标签；`set_event` 不抛异常
- 不要真正运行阻塞式 GUI。

### 集成验证（父级执行）
- 真实 UI 入口：导入→重命名→转写（假 engine）→置 `transcribed`→编辑→落库→重新打开仍为新值。
- 真实模型端到端（可选，父级）：确认状态精确、无百分比显示。

## 5. 编码规范

- Python 3.11，类型注解齐全，`from __future__ import annotations`。
- 每模块职责单一，公开 API 稳定。
- 日志用 `logging`，禁止 `print` 作为业务输出。
- core 禁止 `PySide6`/`PyQt`/`qfluentwidgets`；`funasr`/`torch` 必须懒加载。
- UI 中 `core` 的 import 允许 `TYPE_CHECKING` + 懒加载，避免循环依赖。
- 中文注释可，API 名称统一英文。
- **向后兼容**：v2 的 core API 不得删改签名；v3 只做增量。
- 不允许多个可见导入入口；不允许 `menuBar`/`statusBar`。
