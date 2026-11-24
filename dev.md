# 项目整体框架逻辑
                   Windows Application

                         View
                    (PySide6 GUI)

                           │
                用户操作 / Qt Signal
                           │
                           ▼

                     Controller
               (QThread Task 调度)

                           │
                调用 Engine Service
                           │
                           ▼

                  Interview Engine
               (核心业务逻辑层)

      Audio → VAD → ASR → Speaker → BGE → LLM

                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
      Model Manager                 Data Manager
   (模型下载/加载/更新)          (SQLite/配置文件)


# 项目构建说明
一款基于 PySide6 和 FunASR 的本地化面试录音复盘工具。旨在通过 FunASR (ONNX) 实现全本地化的面试语音转文字，可以考虑利用 Embedding 进行语义分段，最后调用 LLM（本地或云端）生成深度复盘分析。核心技术点在于纯本地化运行以保障数据隐私。

# 使用示例（想达到的效果）
用户上传语音->本地离线分析->分离不同的人声音->以answer-question的形式按照时间顺序排列（看原生其它方法是否能实现分段）->让用户自己配置llm模型（兼容openai格式以及自己本地的模型）->用户点击->分析每个问题回答的结果以及提供正确答案->总结完整的面试评价，指出需要改进的地方
