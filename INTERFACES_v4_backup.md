# 接口契约 v4（Bug 修复专项，Frozen）

> 本文件是 `ui` 修复工作的**唯一标准**。v4 是一次**纯 UI 缺陷修复**，不新增功能、
> 不改 core 语义。core 侧可能需要的极小配合已在第 3 节列出。
>
> **写入范围**：ui subagent 只允许改 `ui/` 与 `main.py`；core subagent 只允许改 `core/`。
> v3 契约已备份为 `INTERFACES_v3_backup.md`（历史参考）。
>
> 环境：PySide6 6.11.1 + PySide6-Fluent-Widgets 1.11.3（qfluentwidgets）。
> 下列 4 个 Bug 均已由父级**复现并定位到根因**，修复方案已给出，请按方案实现并自测。

---

## 1. 已定位的 4 个 Bug（含根因证据）

### Bug 1（严重）：Dark 主题下文字完全看不见

**现象**：`config.theme = "dark"` 时界面文字不可见。

**根因（已用代码验证）**：
qfluentwidgets 的 `setTheme()` 是**通过 `app.setStyleSheet(...)` 注入整套全局 QSS** 来实现主题的。
而 `ui/theme.py::apply_theme()` 在 `setTheme()` 之后调用了：

```python
app.setStyleSheet(build_qss(normalised))   # ← 元凶
```

`QApplication.setStyleSheet()` 是**整体替换**，不是追加。因此我们那 1KB 的局部 QSS
把 qf 的整套 dark 样式**整个冲掉**了，qf 组件退回默认调色板：

```
实测：setTheme(Theme.DARK) 后 app.styleSheet() 长度 = 0（qf 样式走别处/未注入）
      apply_theme 后 app.styleSheet() 长度 = 1107（只剩我们的局部 QSS）
      MainWindow 内 BodyLabel/QLabel 实际 palette: WindowText=#000000
      而我们的 StatusBadge / 标题用硬编码浅色 (#e6edf3) → 浅色字 + 浅色底 = 看不见
```
实测控件调色板（dark 配置下）：
```
WorkspaceView    WindowText=#000000  Window=#efefef   ← 实际是浅色主题！
LibraryPanel     WindowText=#000000  Window=#efefef
workspace title  WindowText=#000000  Window=#efefef
qf BodyLabel     WindowText=#000000  Window=#efefef
```

**修复要求**：
1. **不要在 qf `setTheme()` 之后调用 `app.setStyleSheet()`**。
2. 局部样式改为**只对具体控件** `widget.setStyleSheet(...)`，或用 `setProperty` + 针对性的
   objectName 选择器，**不得**使用会覆盖全局的方式。
3. 优先让 qf 自己管理主题：`setTheme(Theme.DARK)`（并在 app 创建早期调用，最好在
   任何 qf 控件构造前）。
4. `ui/theme.py::apply_theme()` 改为：
   - 调 `setTheme(...)`；
   - **不要** `app.setStyleSheet(build_qss(...))`。
   - 若确实需要给原生 `QTableView`/`QTextBrowser` 上色，请改为在**对应视图内部**
     用 `self._table.setStyleSheet(...)`（局部），并确保浅/深色都对比度足够。
5. `StatusBadge`、`SectionTitle`、`EmptyState`、`_LibraryDelegate` 等自绘/自设样式处，
   **必须基于当前主题的调色板取色**（`theme.palette(name)`），不得假设深色。
   特别注意 `_LibraryDelegate.paint()` 里 `pal["text"]` 等在两套主题下都要可见。
6. 验收：dark 与 light 两种配置下，主窗口内**所有文字**都清晰可读；
   用 palette 断言或截图均需说明。

---

### Bug 2（严重）：右键菜单"删除"点了没反应

**现象**：点右键删除，无任何反应（重命名/重新转写/打开同样失效）。

**根因（已读源码验证）**：
`ui/views/library_panel.py::_on_context_menu()` 用返回值判断用户选了哪一项：

```python
chosen = menu.exec(self._view.viewport().mapToGlobal(pos))
if chosen is open_action: ...
elif chosen is delete_action: ...
```

但 qfluentwidgets 的 `RoundMenu.exec()` **没有返回值**（源码 `menu.py:759` end 处无 return，
即返回 `None`）。因此 `chosen` 恒为 `None`，**所有分支都不成立 → 菜单所有项全部失效**。

**修复要求**：
- 改用 **Action 的 `triggered` 信号**绑定回调，不要把 `exec()` 的返回值当选中项。
  参考写法：
  ```python
  open_action.triggered.connect(lambda: self.open_requested.emit(recording_id))
  rename_action.triggered.connect(lambda: self.rename_requested.emit(recording_id))
  retranscribe_action.triggered.connect(lambda: self.retranscribe_requested.emit(recording_id))
  delete_action.triggered.connect(lambda: self.delete_requested.emit(recording_id))
  menu.exec(global_pos)   # 忽略返回值
  ```
- 注意 `Action` 的 `triggered` 信号签名（qf 的 `Action` 继承自 `QAction`，`triggered` 会带
  `checked` 布尔参数），lambda 需能接收或不接收该参数，避免 `TypeError`。
- 验收：程序化触发右键菜单各项，确认对应信号发出、删除最终从 DB 移除。

---

### Bug 3（性能）：点击已转写录音后要等一会才显示

**现象**：选中录音后 UI 卡住一段时间才渲染。

**根因（已测量）**：
不是 CPU/GPU 慢，而是 **UI 渲染做了 O(n) 的全表行高重算**：
```
实测（无模型、无推理，纯渲染）：
  DB get_detail                 : 1.4 ms
  workspace.set_detail 渲染      : 136 ms   ← 卡顿来源
  set_transcript + resizeRowsToContents:
     50 段 ->  19 ms
    200 段 ->  82 ms
    800 段 -> 311 ms      ← 线性增长
```
`ui/views/table.py::EditableTableView` 在 `dataChanged`/`resizeEvent`/`set_transcript` 时
调用 `resizeRowsToContents()`，而它对**每一行**都要算 `sizeHint`（含换行文本测量），
复杂度 O(行数 × 文本长度)。长录音必然线性卡顿。

**修复要求**：
1. **不要对整表无条件 `resizeRowsToContents()`**。改为：
   - 用自定义 `QStyledItemDelegate.sizeHint()` **按需**计算行高（Qt 只对**可见行**求 sizeHint），
     配合 `verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)` 的
     **惰性**行为；或
   - 保留自适应但**只在必要时**（如首次载入、编辑某一行后）针对**该行**调用；
     或
   - 直接给行高设一个合理固定值 + 依赖 `setWordWrap(True)`，让长文本在 cell 内滚动/换行显示。
2. 无论采用哪种方案，**必须满足 v3 契约"文字要完整显示"**：
   换行后文字可见；列宽可拖动；横向滚动可用。
   （若用固定行高 + wordwrap，需保证行高足够容纳多行文本，或允许该行按需扩展。）
3. 载入大数据集时应做到**感知上的即时**（目标：几百段 < 100ms，或至少不阻塞主线程超过 ~50ms）。
4. 若采用 delegate `sizeHint` 方案，注意与 `setWordWrap(True)` 配合，避免尺寸抖动。
5. 验收：给出 200 段 / 800 段的渲染耗时对比，证明显著改善且文字仍完整可见。

---

### Bug 4（逻辑）：点"待转写"录音仍显示上一条已转写的内容

**现象**：先点过已转写录音，再点待转写录音，右侧仍显示上一条已转写的界面。

**根因**：
`ui/views/workspace_view.py::set_detail()` 只更新数据，**从不重置 tab 选择**，
也不为"无内容"状态切到空缺态。于是 `QTabWidget` 停留在上次的页（如"复盘报告"），
用户看到的是**上一条的残留视图**（实际数据已换，但页面/内容看起来像旧的）。
另外待转写录音的 `transcript/qa/report` 均为空，视图未切换到明确的空状态提示。

**修复要求**：
1. `set_detail()` 必须：
   - **重置到默认 tab（转写文本，index 0）**；
   - 当 `transcript` 为空时，转写 tab 显示明确空状态（"尚未转写，点击「开始转写」"）；
   - 当 `qa_pairs` 为空时，问答 tab 显示空状态；
   - 当 `report` 为空时，报告 tab 显示空状态；
   - 不得残留上一条录音的任何视觉内容。
2. `clear()` 也要重置 tab 与全部空状态。
3. 切换录音时（`set_detail`）应把三个视图**先清空再填充**，避免旧数据闪现。
4. 验收：点"A(已转写/已分析)" → 再点"B(待转写)"，断言：
   - 当前 tab == 0；
   - 转写/问答/报告三个视图都为空状态；
   - 标题与状态徽章显示 B 的信息。

---

## 2. 修复后的验收清单（ui subagent 必须自测并在报告中给出结果）

必须执行：
- `cd /home/qiuqiu/local_Interview_agent && .venv/bin/python -m compileall -q ui main.py`
- `cd /home/qiuqiu/local_Interview_agent && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "import ui.main_window, ui.theme; print('ok')"`

必须自测（offscreen，用假 engine / 临时 DB，不加载模型）：
1. **Bug1**：dark 与 light 两种主题下，构建 MainWindow，断言关键控件文字颜色与背景
   **对比度足够**（例如分别打印 palette 的 WindowText/Window/Base，并断言在 dark 下
   WindowText 是浅色、light 下是深色；或断言 `app.styleSheet()` 未被我们用局部 QSS 覆盖掉 qf）。
   **明确断言：`apply_theme` 之后不得只剩我们的局部 QSS。**
2. **Bug2**：构造 LibraryPanel，程序化触发各 Action 的 `triggered`，断言
   `open/rename/retranscribe/delete` 四个信号都真实发出；并断言删除后 DB 中记录消失。
3. **Bug3**：分别用 200 段与 800 段数据测 `set_detail` 耗时，给出**修复前 vs 修复后**对比，
   并断言文字仍完整显示（例如行高 > 单行高度 / delegate sizeHint 返回 >= 文本所需高度）。
4. **Bug4**：A 已转写 → B 待转写 的切换断言（tab 重置为 0、三视图为空状态、标题正确）。

---

## 3. core 是否需要配合

**本 4 个 Bug 均为 UI 侧问题，core 无需改动。**
core subagent 的唯一任务是：**确认 core 无需改动，并运行回归测试证明未受影响**。
- 若在验证中发现确有 core 侧缺陷（例如 `get_detail` 返回残留数据），
  才可在 `core/` 内做**最小修复**，并在报告中说明。
- 不得改动 core 的公开 API 语义。

core 验证命令：
- `cd /home/qiuqiu/local_Interview_agent && .venv/bin/python -m compileall -q core`
- `cd /home/qiuqiu/local_Interview_agent && .venv/bin/python -m unittest discover -s core/tests`
  （当前基线：**97 tests OK**，不得回归）

---

## 4. 编码规范（沿用）

- Python 3.11，类型注解齐全，`from __future__ import annotations`。
- core 禁止 `PySide6`/`PyQt`/`qfluentwidgets`；`funasr`/`torch` 懒加载。
- 日志用 `logging`，禁止 `print` 作为业务输出。
- **向后兼容**：不得删改既有公开 API 签名；v4 只修行为。
- 修复必须**针对根因**，不要用"加个 sleep / 强制刷新"之类的绕过手段。
- 若为性能做结构性改动（如换 delegate 方案），需在报告中说明取舍与对"文字完整显示"的影响。
