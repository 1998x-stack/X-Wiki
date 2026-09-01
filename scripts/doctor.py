#!/usr/bin/env python3
"""Check whether this Mac is ready to run the X-Wiki pipeline."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from import_voice_memos import discover_recordings
from xwiki_config import Settings


def check(label: str, ok: bool, detail: str) -> bool:
    print(f"{'OK' if ok else 'FAIL':4}  {label}: {detail}")
    return ok


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    settings = Settings.load(repo)
    results = [
        check("macOS", sys.platform == "darwin", platform.platform()),
        check("Apple Silicon", platform.machine() == "arm64", platform.machine()),
        check("Python", sys.version_info >= (3, 10), sys.version.split()[0]),
        check("ffmpeg", shutil.which("ffmpeg") is not None, shutil.which("ffmpeg") or "not found"),
        check("MLX Whisper", importlib.util.find_spec("mlx_whisper") is not None, sys.executable),
        check(
            "pi",
            bool(shutil.which(settings.pi_bin) or Path(settings.pi_bin).exists()),
            settings.pi_bin,
        ),
        check(
            "Voice Memos directory",
            settings.recordings_dir.is_dir(),
            str(settings.recordings_dir),
        ),
    ]
    try:
        count = len(discover_recordings(settings.recordings_dir))
        results.append(check("Voice Memos access", count > 0, f"{count} recording(s)"))
    except (OSError, RuntimeError, sqlite3.DatabaseError) as error:
        results.append(check("Voice Memos access", False, str(error)))

    if (repo / ".git").is_dir():
        remote = subprocess.run(
            ["git", "remote", "get-url", settings.git_remote],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        results.append(
            check(
                "Git remote",
                remote.returncode == 0,
                remote.stdout.strip() or settings.git_remote,
            )
        )
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
