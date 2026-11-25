import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import type { Job, RecordingDetail } from "../lib/types";

type Tab = "transcript" | "qa" | "report";

const STATUS_TEXT: Record<string, string> = {
  imported: "待转写",
  transcribing: "转写中",
  transcribed: "待分析",
  analyzing: "分析中",
  analyzed: "已分析",
  failed: "失败",
};

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

interface WorkspaceProps {
  detail: RecordingDetail;
  job: Job | null;
  onStart: (kind: "transcribe" | "analyze") => void;
  onCancel: () => void;
  onRebuildQa: () => void;
}

export function Workspace({ detail, job, onStart, onCancel, onRebuildQa }: WorkspaceProps) {
  const [tab, setTab] = useState<Tab>("transcript");
  const { recording, transcript, qa_pairs: qaPairs, report } = detail;
  const activeJob = job && ["queued", "running"].includes(job.status) ? job : null;
  const isBusy = recording.status === "transcribing" || recording.status === "analyzing";

  useEffect(() => {
    if (report) setTab("report");
    else if (transcript) setTab("transcript");
  }, [report, transcript]);

  const primaryAction = (() => {
    if (isBusy) {
      return (
        <button className="btn danger" onClick={onCancel}>
          取消任务
        </button>
      );
    }
    if (recording.status === "imported" || recording.status === "failed") {
      return (
        <button className="btn primary" onClick={() => onStart("transcribe")}>
          {transcript ? "重新转写" : "开始转写"}
        </button>
      );
    }
    if (recording.status === "transcribed") {
      return (
        <button className="btn primary" onClick={() => onStart("analyze")}>
          开始分析
        </button>
      );
    }
    return (
      <button className="btn ghost" onClick={() => onStart("analyze")}>
        重新分析
      </button>
    );
  })();

  return (
    <section className="workspace">
      <header className="workspace-head">
        <div>
          <div className="eyebrow">
            <span className={`status ${recording.status}`}>
              {STATUS_TEXT[recording.status] ?? recording.status}
            </span>
            <span>{formatTime(recording.duration)}</span>
            <span>{qaPairs.length} 个问答</span>
            {recording.overall_score != null && (
              <span>{recording.overall_score.toFixed(0)} 分</span>
            )}
          </div>
          <h2>{recording.title}</h2>
          <p className="muted ellipsis">{recording.audio_path}</p>
        </div>
        <div className="actions">{primaryAction}</div>
      </header>

      {(activeJob || job?.status === "failed") && (
        <div className={`progress-card ${job?.status === "failed" ? "failed" : ""}`}>
          <div className="progress-copy">
            <span>{activeJob ? activeJob.message : job?.error || "任务失败"}</span>
            {activeJob?.detail && <small>{activeJob.detail}</small>}
          </div>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{ width: `${activeJob ? Math.max(4, activeJob.percent) : 100}%` }}
            />
          </div>
        </div>
      )}

      {(recording.error_message || job?.error) && (
        <div className="banner error">{job?.error || recording.error_message}</div>
      )}

      <nav className="tabs">
        <button
          className={tab === "transcript" ? "active" : ""}
          onClick={() => setTab("transcript")}
        >
          转写
          <span>{transcript?.segments.length ?? 0}</span>
        </button>
        <button className={tab === "qa" ? "active" : ""} onClick={() => setTab("qa")}>
          问答
          <span>{qaPairs.length}</span>
        </button>
        <button className={tab === "report" ? "active" : ""} onClick={() => setTab("report")}>
          报告
          {report && <span>{report.overall_score.toFixed(0)}</span>}
        </button>
        {tab === "qa" && qaPairs.length > 0 && (
          <button className="link" onClick={onRebuildQa}>
            重新生成问答对
          </button>
        )}
      </nav>

      <div className="tab-body">
        {tab === "transcript" &&
          (transcript?.segments.length ? (
            <div className="segment-list">
              {transcript.segments.map((segment, index) => (
                <div className="segment" key={`${segment.start}-${index}`}>
                  <span className="time">{formatTime(segment.start)}</span>
                  <span className="speaker">{segment.speaker || "未知"}</span>
                  <p>{segment.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <Empty text="还没有转写内容" hint="点击右上角开始转写" />
          ))}

        {tab === "qa" &&
          (qaPairs.length ? (
            <div className="qa-list">
              {qaPairs.map((pair) => (
                <article className="qa-card" key={`${pair.index}-${pair.start}`}>
                  <div className="qa-index">Q{pair.index + 1}</div>
                  <div className="qa-content">
                    <h3>{pair.question || "（无问题文本）"}</h3>
                    <div className="qa-answer">{pair.answer || "（无回答文本）"}</div>
                    <div className="qa-meta">
                      <span>{pair.question_speaker || "面试官"}</span>
                      <span>{formatTime(pair.start)}</span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty text="还没有问答对" hint="完成转写后会自动生成" />
          ))}

        {tab === "report" &&
          (report ? (
            <div className="report">
              <div className="report-overview">
                <div
                  className="score-ring"
                  style={{ "--score": `${Math.max(0, Math.min(100, report.overall_score)) * 3.6}deg` } as CSSProperties}
                >
                  <span>{report.overall_score.toFixed(0)}</span>
                  <small>综合得分</small>
                </div>
                <div>
                  <h3>整体评价</h3>
                  <p>{report.summary || "暂无总结"}</p>
                </div>
              </div>

              {report.improvements.length > 0 && (
                <div className="improvements">
                  <h4>改进建议</h4>
                  <ul>
                    {report.improvements.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="report-items">
                {report.items.map((item) => (
                  <article className="report-item" key={`${item.index}-${item.question}`}>
                    <div className="report-item-head">
                      <span className="qa-index">Q{item.index + 1}</span>
                      <h4>{item.question}</h4>
                      <strong>{item.score.toFixed(0)}</strong>
                    </div>
                    <p className="muted">{item.answer}</p>
                    <div className="report-columns">
                      <div>
                        <h5>优点</h5>
                        <ul>
                          {item.strengths.length ? (
                            item.strengths.map((value) => <li key={value}>{value}</li>)
                          ) : (
                            <li className="muted">暂无</li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <h5>不足</h5>
                        <ul>
                          {item.weaknesses.length ? (
                            item.weaknesses.map((value) => <li key={value}>{value}</li>)
                          ) : (
                            <li className="muted">暂无</li>
                          )}
                        </ul>
                      </div>
                    </div>
                    <div className="suggestion">
                      <strong>建议</strong>
                      <span>{item.suggestion || "暂无"}</span>
                    </div>
                    {item.reference_answer && (
                      <div className="reference">
                        <strong>参考答案</strong>
                        <p>{item.reference_answer}</p>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <Empty text="还没有分析报告" hint="完成转写后点击开始分析" />
          ))}
      </div>
    </section>
  );
}

function Empty({ text, hint }: { text: string; hint: string }) {
  return (
    <div className="empty-state">
      <div className="empty-icon" />
      <p>{text}</p>
      <span>{hint}</span>
    </div>
  );
}
