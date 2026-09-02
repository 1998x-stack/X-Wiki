#!/usr/bin/env python3
"""Summarize the X-Wiki ingestion state (read-only)."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def find_repo(start: Path) -> Path | None:
    """Walk up from a script to the repo root (contains both wiki/ and scripts/)."""
    current = start.resolve()
    while True:
        if (current / "wiki").is_dir() and (current / "scripts").is_dir():
            return current
        if current.parent == current:
            return None
        current = current.parent
    return None

STATUS_LABELS = {
    "raw_ready": "待编译",
    "publish_pending": "待发布",
    "compiled": "已编译",
    "failed": "失败",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=None)
    args = parser.parse_args()
    repo = args.repo or find_repo(Path(__file__).resolve().parents[0])
    if repo is None:
        raise SystemExit("无法定位仓库根（找不到同时含 wiki/ 与 scripts/ 的目录）。")
    db = repo / ".state" / "ingest.sqlite"
    if not db.is_file():
        print(f"尚无摄取状态库：{db}")
        return 0
    connection = sqlite3.connect(db)
    try:
        rows = connection.execute(
            "select raw_path, status, last_error from recordings order by updated_at"
        ).fetchall()
    finally:
        connection.close()

    counts: dict[str, int] = {}
    summarized = False
    for raw_path, status, last_error in rows:
        state = status or "unknown"
        counts[state] = counts.get(state, 0) + 1
        if state == "raw_ready":
            print(f"[待编译] {raw_path}")
            summarized = True
        elif state == "publish_pending":
            print(f"[待发布] {raw_path}")
            summarized = True
        elif state == "failed":
            print(f"[失败]   {raw_path}  {last_error or ''}")
            summarized = True
    if not summarized and rows:
        print("（没有待编译/待发布/失败项，全部已编译。）")
    print("-" * 60)
    print("counts: " + "  ".join(f"{STATUS_LABELS.get(k, k)}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())