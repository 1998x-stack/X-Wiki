from __future__ import annotations

import sqlite3
from pathlib import Path

from import_voice_memos import load_recordings


def test_read_only_database_includes_wal_rows(tmp_path: Path) -> None:
    database = tmp_path / "CloudRecordings.db"
    writer = sqlite3.connect(database)
    writer.execute("pragma journal_mode = wal")
    writer.execute(
        """
        create table ZCLOUDRECORDING (
            ZDATE real,
            ZDURATION real,
            ZCUSTOMLABEL text,
            ZPATH text,
            ZUNIQUEID text
        )
        """
    )
    writer.commit()
    writer.execute(
        "insert into ZCLOUDRECORDING values (?, ?, ?, ?, ?)",
        (1.0, 2.0, "memo", "memo.m4a", "ABC"),
    )
    writer.commit()

    assert load_recordings(database)[0]["ZUNIQUEID"] == "ABC"
    writer.close()
