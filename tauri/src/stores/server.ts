import { create } from "zustand";

import type { Health } from "../lib/types";

type ServerStatus = "booting" | "ready" | "error";

interface ServerStore {
  status: ServerStatus;
  health: Health | null;
  error: string | null;
  setReady: (health: Health) => void;
  setError: (error: string) => void;
}

export const useServerStore = create<ServerStore>((set) => ({
  status: "booting",
  health: null,
  error: null,
  setReady: (health) => set({ status: "ready", health, error: null }),
  setError: (error) => set({ status: "error", error }),
}));
