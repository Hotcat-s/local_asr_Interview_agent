import { useEffect } from "react";

import { api } from "../lib/api";
import { ensureServer } from "../lib/platform";
import { useServerStore } from "../stores/server";

export function useBootstrap() {
  const setReady = useServerStore((state) => state.setReady);
  const setError = useServerStore((state) => state.setError);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      await ensureServer();
      for (let attempt = 0; attempt < 80; attempt += 1) {
        if (cancelled) return;
        try {
          const health = await api.health();
          if (!cancelled) setReady(health);
          return;
        } catch {
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
      }
      if (!cancelled) {
        setError(
          "无法连接本地服务。请确认 Python 边车已启动，或在项目根目录运行 `.venv/bin/python -m backend.main`。",
        );
      }
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, [setReady, setError]);
}
