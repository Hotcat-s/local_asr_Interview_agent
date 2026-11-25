import { invoke } from "@tauri-apps/api/core";

export const API_BASE = "http://127.0.0.1:17493";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Ask the Rust shell to start the Python sidecar. No-op in a plain browser. */
export async function ensureServer(): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke<string>("start_server");
  } catch (error) {
    console.warn("start_server failed", error);
  }
}

export async function pickAudioPath(): Promise<string | null> {
  if (!isTauri()) return null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: false,
    directory: false,
    filters: [
      {
        name: "Audio",
        extensions: ["mp3", "wav", "m4a", "flac", "aac", "ogg", "webm", "mp4"],
      },
    ],
  });
  return typeof selected === "string" ? selected : null;
}
