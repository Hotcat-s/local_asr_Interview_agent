"""Sidecar entrypoint.

Usage:
    python -m backend.main --data-dir ./data --port 17493

The Tauri shell passes ``--parent-pid`` so the sidecar exits if the desktop app
crashes or is killed.
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time

import uvicorn

from backend.app import create_app

logger = logging.getLogger(__name__)


def _watch_parent(parent_pid: int) -> None:
    while True:
        time.sleep(2)
        if os.getppid() != parent_pid:
            logger.warning("Parent process %s exited; shutting down sidecar", parent_pid)
            os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Interview Agent sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=17493)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--parent-pid", type=int, default=None)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.parent_pid:
        threading.Thread(
            target=_watch_parent,
            args=(args.parent_pid,),
            name="parent-watchdog",
            daemon=True,
        ).start()

    app = create_app(args.data_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
