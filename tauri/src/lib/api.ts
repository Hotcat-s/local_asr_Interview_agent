import { API_BASE } from "./platform";
import type {
  Health,
  InterviewReport,
  Job,
  Recording,
  RecordingDetail,
  Settings,
  TranscriptSegment,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = parsed.detail ?? text;
    } catch {
      // keep raw text
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),

  listRecordings: (search?: string) =>
    request<{ recordings: Recording[] }>(
      `/api/recordings${search ? `?search=${encodeURIComponent(search)}` : ""}`,
    ),

  getRecording: (id: number) => request<RecordingDetail>(`/api/recordings/${id}`),

  importPath: (path: string) =>
    request<RecordingDetail>("/api/recordings/import", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<RecordingDetail>("/api/recordings/upload", {
      method: "POST",
      body: form,
    });
  },

  rename: (id: number, title: string) =>
    request<RecordingDetail>(`/api/recordings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  deleteRecording: (id: number) =>
    request<void>(`/api/recordings/${id}`, { method: "DELETE" }),

  transcribe: (id: number) =>
    request<Job>(`/api/recordings/${id}/transcribe`, { method: "POST" }),

  analyze: (id: number) =>
    request<Job>(`/api/recordings/${id}/analyze`, { method: "POST" }),

  cancel: (id: number) =>
    request<Job>(`/api/recordings/${id}/cancel`, { method: "POST" }),

  saveTranscript: (
    id: number,
    segments: TranscriptSegment[],
    regenerateQa = true,
  ) =>
    request<RecordingDetail>(`/api/recordings/${id}/transcript`, {
      method: "PUT",
      body: JSON.stringify({ segments, regenerate_qa: regenerateQa }),
    }),

  rebuildQa: (id: number) =>
    request<RecordingDetail>(`/api/recordings/${id}/qa/rebuild`, { method: "POST" }),

  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),

  getSettings: () => request<Settings>("/api/settings"),

  updateSettings: (payload: Record<string, unknown>) =>
    request<Settings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  testLlm: (llm: Record<string, unknown>) =>
    request<{ ok: boolean; message: string }>("/api/settings/test-llm", {
      method: "POST",
      body: JSON.stringify({ llm }),
    }),

  report: (id: number) =>
    request<{ report: InterviewReport | null }>(`/api/recordings/${id}`).then(
      (detail) => detail.report,
    ),
};
