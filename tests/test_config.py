from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from xwiki_config import (
    Settings,
    default_pi_bin,
    default_recordings_dir,
    env_bool,
    load_dotenv,
)


def test_dotenv_does_not_override_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("XWIKI_LANGUAGE=en\nexport XWIKI_GIT_PUSH='false'\n", encoding="utf-8")
    monkeypatch.setenv("XWIKI_LANGUAGE", "zh")
    monkeypatch.delenv("XWIKI_GIT_PUSH", raising=False)

    load_dotenv(dotenv)

    assert os.environ["XWIKI_LANGUAGE"] == "zh"
    assert os.environ["XWIKI_GIT_PUSH"] == "false"


def test_invalid_dotenv_line_is_rejected(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("NOT AN ASSIGNMENT\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected KEY=VALUE"):
        load_dotenv(dotenv)


def test_boolean_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLAG", "perhaps")
    with pytest.raises(ValueError, match="FLAG"):
        env_bool("FLAG", True)


def test_default_recordings_dir_uses_home(tmp_path: Path) -> None:
    expected = (
        tmp_path
        / "Library"
        / "Group Containers"
        / "group.com.apple.VoiceMemos.shared"
        / "Recordings"
    )
    assert default_recordings_dir(tmp_path) == expected


def test_settings_default_to_chinese(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("XWIKI_"):
            monkeypatch.delenv(name)
    settings = Settings.load(tmp_path)
    assert settings.language == "zh"
    assert settings.llm_model == "iagent/standard"


def test_default_pi_bin_prefers_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_pi = bindir / "pi"
    fake_pi.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_pi.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda name: str(fake_pi) if name == "pi" else None)

    assert default_pi_bin(home=tmp_path) == str(fake_pi)


def test_default_pi_bin_falls_back_to_home_local_bin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    local_pi = tmp_path / ".local" / "bin" / "pi"
    local_pi.parent.mkdir(parents=True)
    local_pi.write_text("#!/bin/sh\n", encoding="utf-8")
    local_pi.chmod(0o755)

    assert default_pi_bin(home=tmp_path) == str(local_pi)


def test_default_pi_bin_absent_returns_bare_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    result = default_pi_bin(home=tmp_path)

    assert result == "pi" or result.endswith("pi")
