# 接口契约 v2（Frozen Interface Contract）

> 本文件是 `core` 与 `ui` 两个子模块并行开发的**唯一契约**，双方必须严格遵守。
> `core` 是**纯 Python 业务逻辑**，禁止 `import PySide6` / `import PyQt`。
> `ui` 只做展示与交互，业务逻辑一律调用 `core`，禁止在 UI 内实现转写 / 分段 / LLM 逻辑。
> 写入范围：core subagent 只允许改 `core/`；ui subagent 只允许改 `ui/` 和 `main.py`。
>
> **v2 变更摘要**：转写与分析解耦；录音库（Recording）取代 session 概念；
> 状态机持久化；分块 LLM 分析；进度细粒度上报；UI 现代化改版。

---

## 0. 本次需求与设计决策（务必先读）

### 0.1 需求清单
1. **转写与分析解耦**：上传音频后只跑 ASR（FunASR），产出转写文本与 Q/A 对；
   用户**主动点击**才触发 LLM 分析。两个阶段独立触发、独立进度、独立结果。
2. **录音库管理**：已上传/已转写/已分析的录音都要能在列表里看到，选中即可查看其
   转写文本、Q/A 对、分析报告。数据全部存本地。
3. **批量转写**：架构上要能扩展（本次不实现 UI，但 core API 与状态字段要预留）。
4. **分块 LLM 分析**：不再"一对 Q/A 调一次"，改为按**数量阈值分批**（默认每批 3 对），
   既保留上下文又避免频繁调用；单批过大时按字符预算再切分。
5. **状态持久化**：录音的 `transcribed` / `analyzed` 状态、时间戳都要存库，且结果可多次重放。

### 0.2 存储方案决策（回答"是否需要数据库"）
**结论：继续用 SQLite（标准库 `sqlite3`），不上 ORM，不上服务端数据库。**

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **SQLite（选中）** | 标准库零依赖、单文件、事务安全、支持"部分状态"增量更新、易备份 | 并发写需串行（本地单用户场景无影响） | ✅ 采用 |
| JSON 文件 | 最简单、易读 | 无法增量更新单条状态、易损坏、无事务、列表查询低效 | ❌ 规模上来就痛 |
| JSON + 文件夹 | 每条录音一个目录，原始结果直观 | 状态需扫目录推断、改名/删除要手工同步、查询要全量读 | ❌ 维护复杂 |
| 嵌入式 KV（如 `platformdirs`+`shelve`） | 简单 | 无结构化查询、并发差、生态弱 | ❌ 不合适 |
| 服务端 DB（Postgres/MySQL） | 强并发 | 违背"纯本地、零部署"目标 | ❌ 违背需求 |

SQLite 已经能表达"转写了/分析了"这种**部分完成状态**（见 0.3 `status` 字段），
并且天然支持录音列表按时间查询。因此保留 SQLite，只是把表结构从"session"升级为
"recording"并补齐状态列。**不引入新依赖。**

### 0.3 数据存储位置
```
data/                          # 由 config.data_dir 决定，默认 "data/"
  interview.db                 # SQLite 主库
  audio/                       # 可选：导入音频的本地副本（本期不强制，仅记录原路径）
config.json                    # 应用配置（LLM / 模型）
```
`AppConfig.db_path` 默认 `data/interview.db`，保持向后兼容。

---

## 1. 目录结构

```
main.py                          # 应用入口，ui 负责
core/
  __init__.py
  exceptions.py                  # 异常定义（新增 CancelledError）
  schemas.py                     # 全部数据模型（dataclass）
  status.py                      # RecordingStatus 状态枚举 + 校验
  progress.py                    # ProgressEvent + ProgressCallback + Stage 常量
  config.py                      # AppConfig / ModelConfig / LLMConfig / AnalysisConfig
  engine.py                      # InterviewEngine 门面（对外唯一入口）
  models/
    __init__.py
    registry.py                  # 本地模型 key -> 相对路径
    manager.py                   # ModelManager
  audio/
    __init__.py
    loader.py                    # AudioLoader：16k mono 归一化 + 时长
    segmenter.py                 # SemanticSegmenter（可选，降级安全）
  asr/
    __init__.py
    engine.py                    # FunASREngine：封装 funasr.AutoModel
  diarization/
    __init__.py
    qa_builder.py                # QABuilder：说话人轮次 -> Q/A 对
  embeddings/
    __init__.py
    bge.py                       # BGEEmbedder（可选）
  llm/
    __init__.py
    client.py                    # LLMClient
    prompts.py                   # prompt 模板（含 batch 模板）
    analyzer.py                  # InterviewAnalyzer（分块分析）
  storage/
    __init__.py
    database.py                  # Database：连接 + schema + 迁移
    repository.py                # Repository：CRUD

ui/
  __init__.py
  app.py                         # 启动引导（加载主题 / QSS）
  theme.py                       # 现代化主题：深色/浅色 QSS + 颜色常量  ★新
  main_window.py                 # 主窗口：三栏布局，无菜单栏
  signals.py                     # UiSignals
  controllers/
    __init__.py
    analysis_controller.py       # AnalysisWorker + AnalysisController（transcribe/analyze 分离）
    library_controller.py        # LibraryController：录音库增删查 + 状态 ★新
    settings_controller.py       # SettingsController
  views/
    __init__.py
    library_panel.py             # 录音库列表（左侧栏）           ★新
    import_view.py               # 导入音频页（空状态 / 拖拽）     ★新
    workspace_view.py            # 工作区：转写/问答/报告 三个 tab  ★新
    transcript_view.py           # 转写文本
    qa_view.py                   # Q/A 对
    report_view.py               # 复盘报告
    progress_panel.py            # 阶段化进度组件（细分阶段+百分比）★新
    settings_dialog.py           # 设置对话框（现代样式）
    widgets.py                   # 通用小组件（Badge/Card/ActionButton）★新
  models/
    __init__.py
    transcript_model.py          # QAbstractTableModel
    qa_model.py                  # QAbstractTableModel
    library_model.py             # 录音库列表模型（QAbstractListModel）★新
  resources/
    app.qss                      # 可选：外置样式表
```

★新 = v2 新增文件。

---

## 2. `core` 对外 API（UI 只能使用这些）

### 2.1 `core.status`

```python
from enum import Enum

class RecordingStatus(str, Enum):
    IMPORTED    = "imported"      # 仅导入，未转写
    TRANSCRIBING= "transcribing"  # 转写中（用于崩溃恢复判断）
    TRANSCRIBED = "transcribed"   # 已转写，未分析
    ANALYZING   = "analyzing"     # 分析中
    ANALYZED    = "analyzed"      # 已分析
    FAILED      = "failed"        # 最近一次操作失败（error_message 有值）
```

校验辅助：`def is_valid_status(value: str) -> bool: ...`

### 2.2 `core.schemas`（在 v1 基础上**新增**，原有类型字段不变）

```python
@dataclass
class TranscriptSegment:
    start: float          # 秒
    end: float            # 秒
    text: str
    speaker: str          # "SPK0" ...

@dataclass
class Transcript:
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration: float = 0.0
    language: str = "zh"
    raw_text: str = ""

@dataclass
class QAPair:
    index: int
    question: str
    answer: str
    question_speaker: str
    answer_speaker: str
    start: float
    end: float

@dataclass
class QAAnalysis:
    index: int
    question: str
    answer: str
    score: float
    strengths: list[str]
    weaknesses: list[str]
    reference_answer: str
    suggestion: str

@dataclass
class InterviewReport:
    overall_score: float
    summary: str
    items: list[QAAnalysis] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    created_at: str = ""

# ---------------- v2 新增 ----------------

@dataclass
class Recording:
    """录音库中的一条记录（取代 v1 的 session dict）。"""
    id: int = 0
    title: str = ""
    audio_path: str = ""
    status: str = "imported"        # core.status.RecordingStatus 的值
    duration: float = 0.0
    language: str = "zh"
    error_message: str = ""
    created_at: str = ""            # ISO8601，导入时间
    updated_at: str = ""            # ISO8601，最近一次状态变更
    transcribed_at: str = ""        # ISO8601，转写完成时间，空=未转写
    analyzed_at: str = ""           # ISO8601，分析完成时间，空=未分析
    qa_count: int = 0               # 冗余计数，便于列表展示
    overall_score: float | None = None  # 冗余，便于列表展示

@dataclass
class RecordingDetail:
    """一条录音的完整内容（按需加载）。"""
    recording: Recording
    transcript: Transcript | None = None
    qa_pairs: list[QAPair] = field(default_factory=list)
    report: InterviewReport | None = None
```

### 2.3 `core.progress`

```python
from dataclasses import dataclass
from typing import Callable

# 阶段常量（UI 用这些值做映射，勿用字面量硬编码）
STAGE_LOAD      = "load"        # 读取/归一化音频
STAGE_MODEL     = "model"       # 加载 ASR 模型
STAGE_VAD       = "vad"
STAGE_ASR       = "asr"
STAGE_DIARIZE   = "diarize"
STAGE_SEGMENT   = "segment"
STAGE_QA        = "qa"          # Q/A 配对
STAGE_LLM       = "llm"
STAGE_SUMMARY   = "summary"     # 整体总结
STAGE_SAVE      = "save"        # 落库
STAGE_DONE      = "done"
STAGE_ERROR     = "error"

@dataclass
class ProgressEvent:
    stage: str
    current: int
    total: int
    percent: float          # 0.0 - 100.0
    message: str
    detail: str = ""        # 可选补充信息（如"第 3/12 段"）

ProgressCallback = Callable[[ProgressEvent], None]

def emit(cb: ProgressCallback | None, stage: str, current: int, total: int,
         message: str, detail: str = "") -> None: ...
```

**进度要求（重要）**：转写阶段必须上报**可感知的细分进度**：
- `STAGE_LOAD`：0→100
- `STAGE_MODEL`：0→100（模型加载，首次较慢，UI 需显示"首次加载模型"）
- `STAGE_ASR`：FunASR 是单次调用，无法内部回调，因此 core 采用
  **分片转写**：若音频时长 > `chunk_seconds`（默认 300s），按静音边界/固定时长切片，
  逐片调用 ASR 并累加 progress（`current/total` 为片数）。单次长音频内部无回调时，
  UI 至少能看到 `percent` 从 0 起跳、`detail` 显示已处理时长/总时长。
  若不便分片，则必须每片完成后上报一次，禁止只在开始/结束各报一次。
- `STAGE_DIARIZE`：0→100（合并说话人）
- `STAGE_QA`：0→100

> core 允许 `transcribe()` 接受 `chunk_seconds: int | None = None` 由 UI 传入。

### 2.4 `core.config`

```python
@dataclass
class ModelConfig:
    asr: str = ""
    vad: str = ""
    punc: str = ""
    spk: str = ""
    device: str = "cuda"

@dataclass
class LLMConfig:
    provider: str = "openai"        # "openai" | "local"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout: float = 120.0

@dataclass
class AnalysisConfig:
    """分块分析参数。"""
    batch_size: int = 3             # 每批分析多少对 Q/A（1=逐题，越大上下文越全）
    max_chars_per_batch: int = 8000 # 单批字符上限，超出则进一步切分
    concurrency: int = 1            # 保留字段，本期串行
    enable_summary: bool = True

@dataclass
class AppConfig:
    models: ModelConfig = field(default_factory=ModelConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    data_dir: str = "data"
    use_embedding_segmentation: bool = False
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    db_path: str = "data/interview.db"
    config_path: str = "config.json"
    chunk_seconds: int = 300        # ASR 分片时长
    theme: str = "dark"             # "dark" | "light"

    @classmethod
    def default(cls) -> "AppConfig": ...
    @classmethod
    def load(cls, path: str | None = None) -> "AppConfig": ...
    def save(self, path: str | None = None) -> None: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig": ...
```
> `from_dict` 必须容忍未知字段与缺失字段（v1 config.json 可直接升级）。

### 2.5 `core.engine.InterviewEngine`（UI 唯一入口）

```python
class InterviewEngine:
    def __init__(self, config: AppConfig | None = None) -> None: ...

    # ---- 阶段一：转写（不碰 LLM）----
    def transcribe(self, audio_path: str,
                   progress: ProgressCallback | None = None,
                   chunk_seconds: int | None = None) -> Transcript: ...

    # ---- Q/A 配对（纯计算，快）----
    def build_qa(self, transcript: Transcript) -> list[QAPair]: ...

    # ---- 阶段二：分析（不碰 ASR）----
    def analyze(self, qa_pairs: list[QAPair],
                llm_config: LLMConfig | None = None,
                progress: ProgressCallback | None = None,
                analysis_config: AnalysisConfig | None = None) -> InterviewReport: ...

    # ---- 便捷全流程（保留，供批量用；UI 默认不用）----
    def run_full(self, audio_path: str,
                 llm_config: LLMConfig | None = None,
                 progress: ProgressCallback | None = None
                 ) -> tuple[Transcript, list[QAPair], InterviewReport]: ...

    def unload(self) -> None: ...
```

**`analyze` 分块语义（需求 4）**：
- 按 `analysis_config.batch_size` 将 `qa_pairs` 切成若干批；
- 每批累计字符数不超过 `max_chars_per_batch`，超出则该批再切；
- 每批**一次** LLM 调用，返回该批所有题的 `QAAnalysis` 数组（JSON 数组）；
  prompt 见 `core/llm/prompts.py:BATCH_ANALYSIS_PROMPT`，必须包含**上下文**：
  同一批内多题共享对话上下文，并要求模型逐题输出、保持 `index` 对齐。
- 单批失败时降级：该批每题为 `score=0` 且 `weaknesses=["分析失败: ..."]`，**不中断**其他批。
- 全部批次完成后，若 `enable_summary`，再调 `summary`（`STAGE_SUMMARY`）。
- 进度：`STAGE_LLM` 的 `current/total` 用**批数**，`detail` 显示"第 k/n 批（第 x-y 题）"。
- 返回的 `report.items` 必须按 `QAPair.index` 升序对齐原始顺序（缺失的题补降级项），
  **不允许乱序或丢题**。

### 2.6 `core.models.manager.ModelManager`
同 v1：
```python
class ModelManager:
    def __init__(self, models_root: str | None = None) -> None: ...
    def resolve(self, key: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def list_available(self) -> list[dict]: ...   # [{key,name,path,exists}]
    def all_paths(self) -> dict[str, str]: ...
```
registry 映射同 v1（asr/vad/punc/spk，目录已存在，禁止联网下载）。

### 2.7 `core.llm`

```python
class LLMClient:
    def __init__(self, config: LLMConfig) -> None: ...
    def chat(self, messages: list[dict], **overrides) -> str: ...
    def chat_json(self, messages: list[dict], **overrides) -> dict: ...
    def chat_json_array(self, messages: list[dict], **overrides) -> list[dict]: ...  # ★新
    def test_connection(self) -> tuple[bool, str]: ...

class InterviewAnalyzer:
    def __init__(self, client: LLMClient,
                 analysis_config: AnalysisConfig | None = None) -> None: ...
    def plan_batches(self, qa_pairs: list[QAPair]) -> list[list[QAPair]]: ...   # ★新，纯函数便于测试
    def analyze_batch(self, batch: list[QAPair]) -> list[QAAnalysis]: ...      # ★新
    def analyze_qa(self, qa: QAPair) -> QAAnalysis: ...                        # 保留（batch_size=1 时用）
    def summarize(self, items: list[QAAnalysis]) -> InterviewReport: ...
```
`chat_json_array` 必须健壮：剥离 ```json 围栏、容忍前后散文、支持对象被包在 `{"items": [...]}` 里、
解析失败抛 `LLMError`。

### 2.8 `core.storage.Repository`（**录音库版，API 变更**）

```python
class Repository:
    def __init__(self, db_path: str) -> None: ...
    def init_db(self) -> None: ...
    def close(self) -> None: ...

    # ---- 录音 CRUD ----
    def create_recording(self, title: str, audio_path: str) -> int: ...
    def get_recording(self, recording_id: int) -> Recording | None: ...
    def list_recordings(self, status: str | None = None,
                        search: str | None = None) -> list[Recording]: ...
    def update_status(self, recording_id: int, status: str,
                      error_message: str = "") -> None: ...
    def update_metadata(self, recording_id: int, *,
                        title: str | None = None,
                        duration: float | None = None,
                        language: str | None = None) -> None: ...
    def delete_recording(self, recording_id: int) -> None: ...
    def mark_analyzed(self, recording_id: int, overall_score: float | None = None) -> None: ...

    # ---- 内容读写 ----
    def save_transcript(self, recording_id: int, transcript: Transcript) -> None: ...
    def load_transcript(self, recording_id: int) -> Transcript | None: ...
    def save_qa_pairs(self, recording_id: int, qa_pairs: list[QAPair]) -> None: ...
    def load_qa_pairs(self, recording_id: int) -> list[QAPair]: ...
    def save_report(self, recording_id: int, report: InterviewReport) -> None: ...
    def load_report(self, recording_id: int) -> InterviewReport | None: ...

    # ---- 汇总 ----
    def get_detail(self, recording_id: int) -> RecordingDetail | None: ...
    def count_recordings(self) -> dict[str, int]: ...   # {"all":n,"transcribed":n,"analyzed":n,...}
```

**数据库表（在 `core/storage/database.py` 内，含 v1→v2 自动迁移）**：
```sql
-- 新表名 recordings；旧的 sessions 表若存在则迁移数据后保留（不删除，安全起见）
CREATE TABLE IF NOT EXISTS recordings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    audio_path     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'imported',
    duration       REAL NOT NULL DEFAULT 0,
    language       TEXT NOT NULL DEFAULT 'zh',
    error_message  TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    transcribed_at TEXT NOT NULL DEFAULT '',
    analyzed_at    TEXT NOT NULL DEFAULT '',
    qa_count       INTEGER NOT NULL DEFAULT 0,
    overall_score  REAL
);
CREATE TABLE IF NOT EXISTS segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    idx INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL,
    text TEXT NOT NULL, speaker TEXT NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS qa_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    idx INTEGER NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL,
    question_speaker TEXT NOT NULL, answer_speaker TEXT NOT NULL,
    start REAL NOT NULL, end REAL NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL UNIQUE,
    overall_score REAL NOT NULL, summary TEXT NOT NULL,
    items_json TEXT NOT NULL, improvements_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```
- `init_schema()` 要幂等；检测 v1 `sessions` 表存在时，把数据搬到 `recordings`
  （`sessions.id` → `recordings.id`，`created_at` 补 `updated_at`，状态按是否有 segments/reports 推断），
  并在 `schema_meta` 写入 `version=2`。迁移失败不得破坏原表。
- 存储总量：一条录音的 transcript/qa/report 就是几张表的行，**不做文件快照**；
  重新转写会**覆盖** `segments` 与 `qa_pairs`，重新分析会**upsert** `reports`
  （与 v1 行为一致，保持简单）。
- `delete_recording` 需显式删除子表（sqlite 的级联已在连接上开启 `PRAGMA foreign_keys=ON`）。

### 2.9 `core.exceptions`
```python
class CoreError(Exception): ...
class ModelNotFoundError(CoreError): ...
class AudioLoadError(CoreError): ...
class TranscriptionError(CoreError): ...
class LLMError(CoreError): ...
class CancelledError(CoreError): ...      # ★新：用于协作式取消
class StorageError(CoreError): ...        # ★新
```
> `CancelledError` 供 `AnalysisController.cancel()` 使用：worker 在 progress 回调里检查取消标志，
> 抛 `core.exceptions.CancelledError`，engine 让它向上传播（不要吞掉），controller 捕获后发 `canceled` 信号。

---

## 3. `ui` 契约

### 3.1 布局总览（无菜单栏，现代化三栏）

```
┌──────────────────────────────────────────────────────────────────┐
│  ⬤ 面试复盘            [导入音频]                    ⚙(左下角)   │
├───────────────┬──────────────────────────────────────────────────┤
│  录音库        │  工作区                                          │
│  (左栏 260px)  │  ┌────────────────────────────────────────────┐  │
│  ┌──────────┐ │  │ 标题 · 状态徽章 · [开始转写] [开始分析]      │  │
│  │ 录音 A ✅ │ │  ├────────────────────────────────────────────┤  │
│  │ 录音 B 📝 │ │  │ [转写文本] [问答对] [复盘报告]              │  │
│  │ 录音 C ⏳ │ │  │  ... 内容区 ...                            │  │
│  └──────────┘ │  └────────────────────────────────────────────┘  │
│  [搜索框]      │  进度面板（转写/分析阶段细分）                    │
│  [筛选 ▾]      │                                                  │
└───────────────┴──────────────────────────────────────────────────┘
```
- **禁止使用 `QMenuBar`**（`self.menuBar()` 不要调用）。文件/分析/帮助等入口改为主界面按钮。
- 设置入口 = **左下角圆形图标按钮**（⚙），不要放菜单栏。
- 保留键盘快捷键（`QShortcut` 挂在窗口上即可）：`Ctrl+O` 导入、`Ctrl+1/2/3` 切 tab、`F5` 转写、`F6` 分析。

### 3.2 转写 / 分析分离（需求 1，关键）

工作区顶部有两个**独立按钮**，各自独立可用/禁用：
- **「开始转写」**：调 `AnalysisController.transcribe(audio_path)`；完成后写入录音库
  （transcript + qa_pairs，状态 → `transcribed`）。
- **「开始分析」**：仅当该录音状态已 `transcribed`/`analyzed` 时可用；
  调 `AnalysisController.analyze(qa_pairs, llm_config)`；完成后写库（report，状态 → `analyzed`）。
- 分析按钮在未转写时必须**置灰并给出 tooltip**"请先转写"。
- 两个阶段各自有进度显示，互不阻塞（同一时刻只允许一个任务运行）。
- 已分析过的录音再次点「开始分析」= 重新分析（覆盖 report）。

### 3.3 `ui.controllers.analysis_controller`

```python
class AnalysisWorker(QObject):
    progress = Signal(object)               # core.ProgressEvent
    transcribed = Signal(object)            # core.Transcript
    analyzed = Signal(object)               # core.InterviewReport
    error = Signal(str)
    canceled = Signal()
    done = Signal()

class AnalysisController(QObject):
    progress = Signal(object)
    transcribed = Signal(object)            # Transcript
    analyzed = Signal(object)               # InterviewReport
    error = Signal(str)
    canceled = Signal()
    busy_changed = Signal(bool)
    stage_changed = Signal(str)             # "transcribe" | "analyze" | ""

    def __init__(self, engine=None, parent=None): ...
    def set_config(self, config: "AppConfig") -> None: ...

    def transcribe(self, audio_path: str) -> None: ...        # 阶段一
    def analyze(self, qa_pairs: list, llm_config) -> None: ... # 阶段二
    def cancel(self) -> None: ...
    def is_busy(self) -> bool: ...
    def unload_models(self) -> None: ...     # 释放显存（不阻塞，可放线程外）
```
- worker 内 `CancelledError` → 发 `canceled`（不要当 error）。
- `transcribe` 结果不自动触发 analyze（**严格解耦**）。
- `run_full` 不再由 UI 使用（保留在 core，UI 不调用）。

### 3.4 `ui.controllers.library_controller` ★新

```python
class LibraryController(QObject):
    library_changed = Signal()                  # 列表需要刷新
    recording_opened = Signal(object)           # core.RecordingDetail
    error = Signal(str)

    def __init__(self, db_path: str = "data/interview.db", parent=None): ...
    def set_db_path(self, path: str) -> None: ...
    def refresh(self, status: str | None = None, search: str | None = None) -> list: ...
    def import_audio(self, audio_path: str, title: str = "") -> int: ...  # 返回 recording_id
    def open_recording(self, recording_id: int) -> None: ...              # 发 recording_opened
    def delete_recording(self, recording_id: int) -> None: ...
    def save_transcript(self, recording_id: int, transcript) -> None: ...
    def save_qa_pairs(self, recording_id: int, qa_pairs) -> None: ...
    def save_report(self, recording_id: int, report) -> None: ...
    def set_status(self, recording_id: int, status: str, error: str = "") -> None: ...
    def counts(self) -> dict: ...
```
> `LibraryController` 直接持有 `core.storage.Repository`。**所有落库都在这里，视图不碰 Repository。**

### 3.5 `ui.controllers.settings_controller`
同 v1，新增：
```python
def save(self, llm_config, model_config=None, analysis_config=None, *, theme=None) -> None: ...
```

### 3.6 `ui.theme` ★新

```python
COLORS = {
    "bg": "#11151c", "panel": "#181e27", "panel_alt": "#1f2733",
    "border": "#2a3441", "text": "#e6edf3", "text_muted": "#8b98a9",
    "accent": "#4f8cff", "accent_hover": "#6ea0ff",
    "success": "#3fb950", "warning": "#d29922", "danger": "#f85149",
}

def build_qss(theme: str = "dark") -> str: ...
def apply_theme(app, theme: str = "dark") -> None: ...
def status_color(status: str) -> str: ...
def status_label(status: str) -> str: ...   # "imported"->"待转写", "transcribed"->"已转写",
                                           # "analyzing"->"分析中", "analyzed"->"已分析",
                                           # "failed"->"失败", "transcribing"->"转写中"
```
- `app.py` 启动时调用 `apply_theme(app, config.theme)`。
- QSS 要覆盖：`QMainWindow`、`QWidget`、`QPushButton`（含 `#accentButton`）、
  `QLineEdit`、`QComboBox`、`QTableView`（含表头/选中行）、`QTabWidget`、
  `QProgressBar`、`QListWidget/QListView`、`QScrollBar`、`QDialog`、`QToolTip`。
- 使用扁平化、圆角（6-8px）、无 heavy border；选中态用 `accent`。

### 3.7 视图要点
- `library_panel.LibraryPanel`：搜索框 + 状态筛选下拉 + 列表（标题/时长/状态徽章/时间）；
  右键菜单：打开、重新转写、删除；双击打开。
  信号：`open_requested(int)`、`delete_requested(int)`、`import_requested()`、`retranscribe_requested(int)`。
- `import_view.ImportView`：空状态引导（大图标 + 说明 + 「选择音频」按钮 + 支持拖拽 `dragEnterEvent/dropEvent`）；
  信号 `audio_selected(str)`。
- `workspace_view.WorkspaceView`：标题栏（标题 + 状态徽章 + 两个动作按钮）+ `QTabWidget`；
  `set_detail(RecordingDetail)`、`clear()`、`set_busy(stage)`。
  信号：`transcribe_requested()`、`analyze_requested()`。
- `progress_panel.ProgressPanel`：显示当前阶段名 + 百分比 + `QProgressBar` + detail 文本；
  `set_event(ProgressEvent)`、`reset()`、`set_indeterminate(bool)`。
- `report_view`：现代化渲染，评分用圆形/大字号，逐题用卡片（HTML）。
- 所有表格：`setShowGrid(False)`、`setAlternatingRowColors(True)`、行高舒适、禁用编辑。

### 3.8 主窗口职责
- 持有 `LibraryController` + `AnalysisController` + `SettingsController`。
- 启动时 `library.refresh()` 填充左栏。
- 选录音 → `library.open_recording(id)` → `workspace.set_detail(detail)`。
- 「开始转写」→ 先确保该录音已入库（导入时已建记录）→ `analysis.transcribe(audio_path)`；
  `progress` → `progress_panel`；`transcribed` → `library.save_transcript` + `save_qa_pairs`
  + `set_status('transcribed')` → 刷新列表与工作区。
- 「开始分析」→ `analysis.analyze(qa_pairs, config.llm)`；`analyzed` →
  `library.save_report` + `mark_analyzed` → 刷新。
- 关闭窗口时若有任务运行 → `cancel()`。

---

## 4. 运行与验证

- 环境：`uv run python main.py`
- 依赖（已安装）：funasr 1.3.16、torch 2.5.1+cu124、PySide6、openai、httpx[socks]、numpy、soundfile、librosa。
- core 自测：`uv run python -m unittest discover -s core/tests`
  - 必须包含：**批量分批 `plan_batches` 的纯数据测试**（含字符上限切分、顺序保持）、
    `chat_json_array` 解析测试、`Recording` 状态流转与 v1→v2 迁移测试、
    `Repository` 全量 round-trip、`update_status` 时间戳写入。
  - 不得依赖真实音频 / GPU / 网络。
- ui 自测：`QT_QPA_PLATFORM=offscreen uv run python -c "import ui.main_window; ui.main_window.MainWindow(config=...)"` 能构建。
- 集成验证（父级执行）：构造假 engine 跑 controller，确认 transcribe/analyze 分离、
  进度事件序列、状态落库。

## 5. 编码规范

- Python 3.11，类型注解齐全，`from __future__ import annotations`。
- 每个模块职责单一（最小原子性），公开 API 稳定。
- 日志用标准库 `logging`，禁止 `print` 作为业务输出。
- core 禁止 `import PySide6`/`PyQt`；`funasr`/`torch` 必须懒加载。
- 中文注释可，API 名称统一英文。
- 向后兼容：保留 v1 的 `Transcript`/`QAPair`/`QAAnalysis`/`InterviewReport` 字段名；
  `Repository` 的 v1 方法名（`create_session` 等）**可以删除**，但需在本文件同步 API 供 ui 使用。
