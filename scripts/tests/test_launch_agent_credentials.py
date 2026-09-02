from __future__ import annotations

import json
from pathlib import Path

import pytest
from install_launch_agent import (
    missing_credential_envs,
    provider_credential_envs,
    provider_env_refs,
)
from xwiki_config import Settings

MODELS = {
    "providers": {
        "iagent": {
            "baseUrl": "https://iagent.iauto.com/v1",
            "api": "openai-completions",
            "apiKey": "$IAUTO_API_KEY",
            "authHeader": True,
            "models": [
                {
                    "id": "iagent/standard",
                    "maxTokens": 16384,
                    "apiKey": "$IAUTO_BASE_URL",
                }
            ],
        }
    }
}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        repo=tmp_path,
        recordings_dir=tmp_path / "Recordings",
        language="zh",
        whisper_model="mlx",
        llm_provider="iagent",
        llm_model="iagent/standard",
        pi_bin="pi",
        min_age_seconds=60,
        scan_interval_seconds=60,
        compile_timeout_seconds=900,
        git_push=True,
        git_remote="origin",
        git_branch="main",
    )


def test_credentials_split_into_present_and_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = tmp_path / "models.json"
    models.write_text(json.dumps(MODELS), encoding="utf-8")
    monkeypatch.setenv("IAUTO_API_KEY", "secret-key")
    monkeypatch.delenv("IAUTO_BASE_URL", raising=False)

    present, missing = provider_env_refs(_settings(tmp_path), models)
    assert present == ["IAUTO_API_KEY"]
    assert missing == ["IAUTO_BASE_URL"]

    creds = provider_credential_envs(_settings(tmp_path), models)
    assert creds == {"IAUTO_API_KEY": "secret-key"}

    assert missing_credential_envs(_settings(tmp_path), models) == ["IAUTO_BASE_URL"]


def test_missing_models_file_returns_empty(tmp_path: Path) -> None:
    assert provider_credential_envs(_settings(tmp_path), tmp_path / "nope.json") == {}
    assert missing_credential_envs(_settings(tmp_path), tmp_path / "nope.json") == []


def test_unknown_provider_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "models.json"
    models.write_text(json.dumps(MODELS), encoding="utf-8")
    monkeypatch.setenv("IAUTO_API_KEY", "secret-key")
    settings = _settings(tmp_path)
    other = Settings(
        **{
            **settings.__dict__,
            "llm_provider": "other",
        }
    )

    assert missing_credential_envs(other, models) == []


def test_invalid_model_json_ignored(tmp_path: Path) -> None:
    models = tmp_path / "models.json"
    models.write_text("not json", encoding="utf-8")
    assert provider_credential_envs(_settings(tmp_path), models) == {}