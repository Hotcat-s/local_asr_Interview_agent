# Interview Lab 架构说明

本地化 AI 面试复盘工具。桌面端用 **Tauri 2 + React** 重写，保留原有 Python 推理能力，作为 **FastAPI 边车（sidecar）** 运行在后台。

> 旧版 PySide6 + QThread 的 GUI 层已移除，`core/` 中的业务与推理逻辑完整保留。

## 1. 整体形态

```
┌──────────────────────────────────────────────────────────────┐
│  Tauri 2 桌面进程 (Rust)                                      │
│  ├─ 窗口 / 打包 / 原生文件对话框                                │
│  ├─ 启动与守护 Python 边车，端口探活，退出时回收子进程            │
│  └─ WebView 加载 React 前端                                    │
│        │                                                      │
│        │ HTTP + SSE  http://127.0.0.1:17493                    │
│        ▼                                                      │
│  Python 边车 (uvicorn + FastAPI)                              │
│  ├─ REST API：录音库 / 转写 / 问答 / 报告 / 设置                │
│  ├─ 串行任务队列（单 worker 线程，一次只跑一个重任务）            │
│  ├─ SSE 事件流：任务进度、录音状态变更                          │
│  └─ core/：FunASR 转写、VAD、标点、说话人分离、LLM 分析          │
└──────────────────────────────────────────────────────────────┘
```

关键原则：

- **推理全部留在 Python**。ASR / VAD / 标点 / 说话人模型约 2.1GB，全部本地运行；只有 LLM 走远端 OpenAI 兼容接口。
- **一次只跑一个重任务**。模型加载占显存，任务队列串行执行，避免并发冲突；HTTP 服务本身仍可并发响应。
- **Rust 只做壳**。不参与推理，负责进程生命周期、窗口、文件选择与打包。
- **前端无状态持久化**。所有数据以边车内的 SQLite 为准，前端只做展示与乐观刷新。

## 2. 目录结构

```
.
├── core/                     # 复用：无 GUI 依赖的核心层
│   ├── engine.py             # InterviewEngine：transcribe / build_qa / analyze / unload
│   ├── config.py             # AppConfig、LLMConfig、ModelConfig
│   ├── schemas.py            # Recording / Transcript / QAPair / InterviewReport ...
│   ├── status.py             # 录音状态枚举
│   ├── progress.py           # ProgressEvent 与阶段常量
│   ├── llm/client.py         # OpenAI 兼容客户端 + 容错 JSON 解析
│   ├── storage/              # SQLite schema v2 与 Repository
│   └── models/               # 模型注册表与本地权重（不进 Git）
├── backend/                  # 新增：Python 边车
│   ├── main.py               # 入口：--host/--port/--data-dir/--parent-pid
│   ├── app.py                # create_app()，挂载 /api 路由与 CORS
│   ├── runtime.py            # RuntimePaths / AppState（懒加载引擎、配置、仓库）
│   ├── schemas.py            # 请求体 Pydantic 模型
│   ├── deps.py               # get_state 依赖
│   ├── services/
│   │   ├── events.py         # EventBus（SSE 广播，每客户端独立队列）
│   │   └── tasks.py          # TaskQueue（串行执行、取消、状态回滚）
│   ├── routes/               # system / recordings / jobs / settings / events
│   └── tests/test_api.py     # FakeEngine 驱动的 API 测试
├── tauri/                    # 桌面外壳 + 前端
│   ├── src/                  # React 18 + TypeScript
│   │   ├── lib/              # api.ts、types.ts、platform.ts
│   │   ├── hooks/            # useBootstrap（等待边车就绪）、useLibrary（数据与 SSE）
│   │   ├── stores/           # zustand：边车启动状态
│   │   ├── components/       # Sidebar / Workspace / SettingsModal
│   │   └── styles.css        # 深色主题设计系统
│   └── src-tauri/
│       ├── src/lib.rs        # 边车启动/探活/回收、四个 command
│       ├── tauri.conf.json   # 窗口、构建、打包配置
│       └── capabilities/     # 权限声明
├── data/                     # 运行时数据（已忽略）：audio/、interview.db、config.json
└── ARCHITECTURE.md
```

## 3. 运行时数据

| 位置 | 内容 |
| --- | --- |
| `data/interview.db` | SQLite（schema v2）：recordings / segments / qa_pairs / reports |
| `data/config.json` | 应用配置：模型目录、LLM、分析参数、分块秒数 |
| `data/audio/` | 导入的音频副本（上传或本地路径导入都会复制到此） |
| `core/models/` | 本地模型权重，需单独下载，不入 Git |

数据目录解析顺序（`backend/runtime.py`）：命令行 `--data-dir` → 环境变量 `INTERVIEW_DATA_DIR` → 仓库 `data/`。首次运行若仓库根部存在旧 `config.json`，会复制进数据目录。

## 4. 两阶段流水线

```
导入音频
  └─ POST /api/recordings/import        → status=imported
        │
        ├─ POST /api/recordings/{id}/transcribe
        │     status=transcribing
        │     engine.transcribe()  ── VAD / ASR / 标点 / 说话人
        │     engine.build_qa()    ── 按问答配对切分
        │     status=transcribed
        │
        └─ POST /api/recordings/{id}/analyze
              status=analyzing
              engine.analyze()     ── 逐题评分 + 总评报告
              status=analyzed（写入 overall_score）
```

- 任务通过 `TaskQueue` 串行执行；同一录音重复提交会被拒绝。
- `POST /{id}/cancel` 置位取消事件，worker 在进度回调处中断，并把状态回滚到任务开始前的值。
- 失败时写回 `failed` 与 `error_message`，前端可直接展示。

## 5. HTTP API

所有接口前缀 `/api`（另有 `/health` 根路径，供 Rust 探活）。

### 系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 版本、引擎是否加载、任务数 |
| GET | `/models` | 本地模型清单（key/name/path/exists） |
| POST | `/models/reload` | 重新扫描模型目录 |
| POST | `/engine/unload` | 释放引擎与显存 |

### 录音库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/recordings?status=&search=` | 列表，按更新时间倒序 |
| POST | `/recordings/import` | 按本地路径导入（复制到 `data/audio/`） |
| POST | `/recordings/upload` | multipart 上传导入 |
| GET | `/recordings/{id}` | 详情：录音 + 转写 + 问答 + 报告 |
| PATCH | `/recordings/{id}` | 重命名 |
| DELETE | `/recordings/{id}` | 删除录音及其关联数据 |
| POST | `/recordings/{id}/transcribe` | 入队转写 |
| POST | `/recordings/{id}/analyze` | 入队分析 |
| POST | `/recordings/{id}/cancel` | 取消当前任务 |
| PUT | `/recordings/{id}/transcript` | 保存人工修订的转写，可选 `regenerate_qa` |
| PUT | `/recordings/{id}/qa` | 保存人工修订的问答对 |
| POST | `/recordings/{id}/qa/rebuild` | 基于现有转写重建问答对 |

### 任务与设置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/jobs` | 当前与历史任务 |
| GET | `/jobs/{job_id}` | 单任务详情 |
| GET | `/settings` | 读取配置 |
| PUT | `/settings` | 更新配置并落盘 |
| POST | `/settings/test-llm` | 测试 LLM 连通性 |

### 事件流

`GET /api/events` 返回 `text/event-stream`，15 秒心跳。消息体形如：

```json
{"type": "job", "job": {"id": "...", "recording_id": 3, "status": "running", "stage": "asr", "percent": 42, "message": "..."}}
{"type": "recording", "recording_id": 3, "status": "transcribing"}
```

前端订阅 SSE 做实时刷新，并以 1.5 秒轮询作为兜底。

## 6. 桌面外壳（Rust）

`tauri/src-tauri/src/lib.rs` 暴露四个 command：

- `start_server()`：若端口已开直接返回；否则启动边车并转发 stdout/stderr 到前端事件 `sidecar-log`。
- `stop_server()`：结束子进程。
- `server_info()`：URL、运行状态、数据目录、模式（`python` / `bundled`）。
- `get_data_dir()`：数据目录绝对路径。

边车启动策略：

1. 环境变量 `INTERVIEW_SIDECAR` 指向的可执行文件；
2. 打包资源目录中的 `interview-server`（PyInstaller 产物）；
3. 开发态回退到仓库内的 `.venv/bin/python -m backend.main`。

启动时传入 `--parent-pid`，边车内的看门狗线程在父进程消失后自行退出；`RunEvent::Exit` 时 Rust 侧也会主动 kill 子进程，双向兜底。

前端启动流程：`useBootstrap` → `ensureServer()`（Tauri 下 invoke `start_server`）→ 轮询 `/health` 最多 80 次 → 就绪后加载录音库。

## 7. 开发与构建

### 后端（可独立运行、独立测试）

```bash
# 只跑 API + 任务队列，不加载模型
.venv/bin/python -m backend.main --port 17493 --data-dir ./data

# 测试使用 FakeEngine，不需要模型权重
.venv/bin/python -m pytest backend/tests -q
```

### 前端

```bash
cd tauri
npm install
npm run dev      # Vite，端口 5173
npm run build    # tsc --noEmit + vite build → tauri/dist
```

### 桌面

```bash
cd tauri
npm run tauri dev
npm run tauri build
```

Linux 构建需要系统依赖：`webkit2gtk-4.1`、`gtk+-3.0`、`libsoup-3.0`、`pkg-config`、`librsvg2-dev`、`patchelf` 等。macOS 需 Xcode Command Line Tools；Windows 需 WebView2（系统自带）。

### 打包 Python 边车（可选）

生产环境可用 PyInstaller 将 `backend.main` 打成单文件，放到 `tauri/src-tauri/binaries/interview-server`，或通过 `INTERVIEW_SIDECAR` 指定路径。权重与 `data/` 不打进包内，首次启动时由用户指定模型目录。

## 8. 迁移路线

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| Tauri + React 前端替换 Qt | 已完成 | 录音库、工作台、设置弹窗全部迁移 |
| FastAPI 边车承载流水线 | 已完成 | 复用 `core/`，新增任务队列与 SSE |
| 打包与分发 | 待办 | PyInstaller 边车 + Tauri 安装包 |
| ASR 推理 Rust 化 | 后续 | 可换 sherpa-onnx / ONNX Runtime，边车逐步瘦身 |

Rust 化的判断标准：只有在**软件启动速度、内存占用、跨平台分发**上确有收益时才迁移推理；在此之前，Python 边车是成本最低、风险最小的方案。
