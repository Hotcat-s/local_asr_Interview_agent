import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { Settings } from "../lib/types";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMessage(null);
    api
      .getSettings()
      .then(setSettings)
      .catch((error: unknown) =>
        setMessage(error instanceof Error ? error.message : String(error)),
      );
  }, [open]);

  if (!open) return null;

  const updateLlm = (key: keyof Settings["llm"], value: string | number) => {
    setSettings((current) =>
      current ? { ...current, llm: { ...current.llm, [key]: value } } : current,
    );
  };

  async function save() {
    if (!settings) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await api.updateSettings({
        llm: settings.llm,
        models: { device: settings.models.device },
        analysis: settings.analysis,
        chunk_seconds: settings.chunk_seconds,
      });
      setSettings(updated);
      setMessage("已保存");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    if (!settings) return;
    setTesting(true);
    setMessage(null);
    try {
      const result = await api.testLlm(settings.llm as unknown as Record<string, unknown>);
      setMessage(result.message);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <header className="modal-head">
          <div>
            <h3>设置</h3>
            <p className="muted">本地配置保存在数据目录的 config.json</p>
          </div>
          <button className="icon" onClick={onClose}>
            ×
          </button>
        </header>

        {!settings ? (
          <p className="muted">正在加载…</p>
        ) : (
          <div className="form">
            <label>
              <span>LLM Base URL</span>
              <input
                value={settings.llm.base_url}
                onChange={(event) => updateLlm("base_url", event.target.value)}
                placeholder="https://api.openai.com/v1"
              />
            </label>
            <label>
              <span>API Key</span>
              <input
                type="password"
                value={settings.llm.api_key}
                onChange={(event) => updateLlm("api_key", event.target.value)}
                placeholder="sk-..."
              />
            </label>
            <div className="form-row">
              <label>
                <span>模型</span>
                <input
                  value={settings.llm.model}
                  onChange={(event) => updateLlm("model", event.target.value)}
                />
              </label>
              <label>
                <span>Temperature</span>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={settings.llm.temperature}
                  onChange={(event) =>
                    updateLlm("temperature", Number(event.target.value))
                  }
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                <span>推理设备</span>
                <select
                  value={settings.models.device}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      models: { ...settings.models, device: event.target.value },
                    })
                  }
                >
                  <option value="cpu">CPU</option>
                  <option value="cuda">CUDA</option>
                </select>
              </label>
              <label>
                <span>分块时长（秒）</span>
                <input
                  type="number"
                  min="30"
                  max="1800"
                  value={settings.chunk_seconds}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      chunk_seconds: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>
            <label>
              <span>分析批大小</span>
              <input
                type="number"
                min="1"
                max="20"
                value={settings.analysis.batch_size}
                onChange={(event) =>
                  setSettings({
                    ...settings,
                    analysis: {
                      ...settings.analysis,
                      batch_size: Number(event.target.value),
                    },
                  })
                }
              />
            </label>

            {message && <div className="form-message">{message}</div>}

            <div className="modal-actions">
              <button className="btn ghost" onClick={testConnection} disabled={testing}>
                {testing ? "测试中…" : "测试连接"}
              </button>
              <button className="btn primary" onClick={save} disabled={saving}>
                {saving ? "保存中…" : "保存设置"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
