#!/usr/bin/env python3
"""Render and install the X-Wiki Voice Memos launchd agent."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
from pathlib import Path


LABEL = "com.1998x.x-wiki.voice-ingest"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=Path(
            "/System/Volumes/Data/Users/x/Library/Group Containers/"
            "group.com.apple.VoiceMemos.shared/Recordings"
        ),
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{LABEL}.plist"
    logs = repo / ".state" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            "/usr/bin/python3",
            str(repo / "scripts" / "process_voice_memos.py"),
        ],
        "WorkingDirectory": str(repo),
        "WatchPaths": [str(args.recordings_dir.resolve())],
        "StartInterval": 300,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "launchd.out.log"),
        "StandardErrorPath": str(logs / "launchd.err.log"),
        "EnvironmentVariables": {
            "HOME": str(Path.home()),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "PYTHONPATH": str(Path.home() / "Library/Python/3.9/lib/python/site-packages"),
            "PYTHONUNBUFFERED": "1",
        },
    }
    plist_path.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(plist_path)], check=False)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=True)
    subprocess.run(["launchctl", "enable", f"{domain}/{LABEL}"], check=True)
    print(plist_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
