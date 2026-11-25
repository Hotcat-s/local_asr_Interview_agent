import type { Recording, RecordingStatus } from "../lib/types";

const STATUS_TEXT: Record<RecordingStatus, string> = {
  imported: "待转写",
  transcribing: "转写中",
  transcribed: "待分析",
  analyzing: "分析中",
  analyzed: "已分析",
  failed: "失败",
};

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "--:--";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

interface SidebarProps {
  recordings: Recording[];
  selectedId: number | null;
  importing: boolean;
  onSelect: (id: number) => void;
  onImport: () => void;
  onDelete: (id: number) => void;
  onSettings: () => void;
}

export function Sidebar({
  recordings,
  selectedId,
  importing,
  onSelect,
  onImport,
  onDelete,
  onSettings,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">IL</div>
        <div>
          <h1>Interview Lab</h1>
          <p>本地面试复盘工作台</p>
        </div>
      </div>

      <button className="btn primary block" onClick={onImport} disabled={importing}>
        {importing ? "正在导入…" : "+ 导入录音"}
      </button>

      <div className="list-head">
        <span>录音库</span>
        <span className="count">{recordings.length}</span>
      </div>

      <div className="recording-list">
        {recordings.length === 0 && (
          <div className="empty-list">
            <p>还没有录音</p>
            <span>导入一段面试音频开始复盘</span>
          </div>
        )}
        {recordings.map((recording) => (
          <div
            key={recording.id}
            role="button"
            tabIndex={0}
            className={`recording-item ${selectedId === recording.id ? "active" : ""}`}
            onClick={() => onSelect(recording.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") onSelect(recording.id);
            }}
          >
            <div className="recording-top">
              <span className="recording-title">{recording.title}</span>
              <span className={`status ${recording.status}`}>
                {STATUS_TEXT[recording.status]}
              </span>
            </div>
            <div className="recording-meta">
              <span>{formatDuration(recording.duration)}</span>
              <span>{recording.qa_count} 个问答</span>
              {recording.overall_score != null && (
                <span className="score-mini">{recording.overall_score.toFixed(0)} 分</span>
              )}
            </div>
            {recording.error_message && (
              <div className="recording-error">{recording.error_message}</div>
            )}
            <button
              className="icon danger"
              title="删除录音"
              onClick={(event) => {
                event.stopPropagation();
                if (window.confirm(`删除「${recording.title}」？`)) {
                  onDelete(recording.id);
                }
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <button className="btn ghost block" onClick={onSettings}>
        设置
      </button>
    </aside>
  );
}
