import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import { API_BASE } from "../lib/platform";
import type { Job, Recording, RecordingDetail } from "../lib/types";

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function useLibrary(ready: boolean) {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<RecordingDetail | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const selectedRef = useRef<number | null>(null);

  useEffect(() => {
    selectedRef.current = selectedId;
  }, [selectedId]);

  const refreshRecordings = useCallback(async () => {
    try {
      const payload = await api.listRecordings();
      setRecordings(payload.recordings);
    } catch (err) {
      setError(toMessage(err));
    }
  }, []);

  const refreshDetail = useCallback(async (id: number) => {
    try {
      setDetail(await api.getRecording(id));
    } catch (err) {
      setError(toMessage(err));
    }
  }, []);

  const select = useCallback((id: number) => {
    setSelectedId(id);
    setDetail(null);
    setJob(null);
    setError(null);
  }, []);

  useEffect(() => {
    if (selectedId != null) void refreshDetail(selectedId);
  }, [selectedId, refreshDetail]);

  useEffect(() => {
    if (ready) void refreshRecordings();
  }, [ready, refreshRecordings]);

  useEffect(() => {
    if (!ready) return;
    const source = new EventSource(`${API_BASE}/api/events`);
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          type: string;
          job?: Job;
          recording_id?: number;
        };
        if (payload.type === "job" && payload.job) {
          const incoming = payload.job;
          setJob((current) => (current?.id === incoming.id ? incoming : current));
          if (["succeeded", "failed", "cancelled"].includes(incoming.status)) {
            void refreshRecordings();
            const id = selectedRef.current;
            if (id != null && id === incoming.recording_id) void refreshDetail(id);
          }
        }
        if (payload.type === "recording" && payload.recording_id != null) {
          void refreshRecordings();
          const id = selectedRef.current;
          if (id != null && id === payload.recording_id) void refreshDetail(id);
        }
      } catch {
        // Ignore malformed or unrelated events.
      }
    };
    return () => source.close();
  }, [ready, refreshRecordings, refreshDetail]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getJob(job.id);
        setJob(next);
        if (!["queued", "running"].includes(next.status)) {
          void refreshRecordings();
          const id = selectedRef.current;
          if (id != null && id === next.recording_id) void refreshDetail(id);
        }
      } catch {
        // SSE remains the primary channel; polling is only a fallback.
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job, refreshRecordings, refreshDetail]);

  const importPath = useCallback(
    async (path: string) => {
      setImporting(true);
      setError(null);
      try {
        const data = await api.importPath(path);
        setSelectedId(data.recording.id);
        setDetail(data);
        setJob(null);
        await refreshRecordings();
        return data;
      } catch (err) {
        setError(toMessage(err));
        throw err;
      } finally {
        setImporting(false);
      }
    },
    [refreshRecordings],
  );

  const uploadFile = useCallback(
    async (file: File) => {
      setImporting(true);
      setError(null);
      try {
        const data = await api.upload(file);
        setSelectedId(data.recording.id);
        setDetail(data);
        setJob(null);
        await refreshRecordings();
        return data;
      } catch (err) {
        setError(toMessage(err));
        throw err;
      } finally {
        setImporting(false);
      }
    },
    [refreshRecordings],
  );

  const start = useCallback(
    async (kind: "transcribe" | "analyze") => {
      const id = selectedRef.current;
      if (id == null) return;
      setError(null);
      try {
        const next =
          kind === "transcribe" ? await api.transcribe(id) : await api.analyze(id);
        setJob(next);
        await refreshRecordings();
      } catch (err) {
        setError(toMessage(err));
      }
    },
    [refreshRecordings],
  );

  const cancel = useCallback(async () => {
    const id = selectedRef.current;
    if (id == null) return;
    try {
      setJob(await api.cancel(id));
    } catch (err) {
      setError(toMessage(err));
    }
  }, []);

  const remove = useCallback(
    async (id: number) => {
      try {
        await api.deleteRecording(id);
        if (selectedRef.current === id) {
          setSelectedId(null);
          setDetail(null);
          setJob(null);
        }
        await refreshRecordings();
      } catch (err) {
        setError(toMessage(err));
      }
    },
    [refreshRecordings],
  );

  const rebuildQa = useCallback(async () => {
    const id = selectedRef.current;
    if (id == null) return;
    try {
      setDetail(await api.rebuildQa(id));
    } catch (err) {
      setError(toMessage(err));
    }
  }, []);

  return {
    recordings,
    selectedId,
    detail,
    job,
    error,
    importing,
    select,
    importPath,
    uploadFile,
    start,
    cancel,
    remove,
    rebuildQa,
    dismissError: () => setError(null),
  };
}
