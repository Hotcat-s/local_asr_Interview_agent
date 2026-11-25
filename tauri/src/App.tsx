import { useRef, useState, type DragEvent } from "react";

import { SettingsModal } from "./components/SettingsModal";
import { Sidebar } from "./components/Sidebar";
import { Workspace } from "./components/Workspace";
import { useBootstrap } from "./hooks/useBootstrap";
import { useLibrary } from "./hooks/useLibrary";
import { pickAudioPath } from "./lib/platform";
import { useServerStore } from "./stores/server";

export default function App() {
  useBootstrap();
  const status = useServerStore((state) => state.status);
  const bootError = useServerStore((state) => state.error);
  const library = useLibrary(status === "ready");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function handleImport() {
    const path = await pickAudioPath();
    if (path) {
      try {
        await library.importPath(path);
      } catch {
        // Error is surfaced by the hook.
      }
      return;
    }
    fileInput.current?.click();
  }

  async function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    try {
      await library.uploadFile(file);
    } catch {
      // Error is surfaced by the hook.
    }
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    void handleFiles(event.dataTransfer.files);
  }

  if (status === "booting") {
    return (
      <div className="boot">
        <div className="spinner" />
        <h1>Interview Lab</h1>
        <p>正在启动本地服务…</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="boot">
        <div className="boot-error">!</div>
        <h1>本地服务未就绪</h1>
        <p>{bootError}</p>
        <code>.venv/bin/python -m backend.main</code>
      </div>
    );
  }

  return (
    <div className="app" onDragOver={(event) => event.preventDefault()} onDrop={handleDrop}>
      <Sidebar
        recordings={library.recordings}
        selectedId={library.selectedId}
        importing={library.importing}
        onSelect={library.select}
        onImport={handleImport}
        onDelete={library.remove}
        onSettings={() => setSettingsOpen(true)}
      />

      <main className="main">
        {library.error && (
          <div className="banner error">
            <span>{library.error}</span>
            <button className="icon" onClick={library.dismissError}>
              ×
            </button>
          </div>
        )}

        {library.detail ? (
          <Workspace
            detail={library.detail}
            job={library.job}
            onStart={library.start}
            onCancel={library.cancel}
            onRebuildQa={library.rebuildQa}
          />
        ) : (
          <Welcome onImport={handleImport} importing={library.importing} />
        )}
      </main>

      <input
        ref={fileInput}
        type="file"
        accept="audio/*,.mp3,.wav,.m4a,.flac,.aac,.ogg,.webm,.mp4"
        hidden
        onChange={(event) => {
          void handleFiles(event.target.files);
          event.target.value = "";
        }}
      />

      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

function Welcome({ onImport, importing }: { onImport: () => void; importing: boolean }) {
  return (
    <div className="welcome">
      <div className="welcome-glow" />
      <p className="eyebrow">LOCAL FIRST</p>
      <h1>把面试录音变成可复盘的问答与报告</h1>
      <p className="welcome-copy">
        音频、转写、问答和报告都保存在本机。导入一段录音，先转写，再让 LLM
        逐题评估。
      </p>
      <button className="btn primary large" onClick={onImport} disabled={importing}>
        {importing ? "正在导入…" : "导入第一段录音"}
      </button>
      <p className="welcome-hint">也可以把音频文件拖到这里</p>
      <div className="pipeline">
        <span>音频</span>
        <i />
        <span>转写</span>
        <i />
        <span>问答</span>
        <i />
        <span>评估报告</span>
      </div>
    </div>
  );
}
