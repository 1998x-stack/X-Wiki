"""Shared, environment-aware configuration for X-Wiki scripts."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def load_dotenv(path: Path) -> None:
    """Load a small, dependency-free subset of dotenv without overriding the shell."""
    if not path.is_file():
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"invalid .env line {line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            raise ValueError(f"invalid .env key on line {line_number}: {key!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of: 1/0, true/false, yes/no, on/off")


def env_int(name: str, default: int, *, minimum: int = 0) -> int:
    value = int(os.environ.get(name, default))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def default_recordings_dir(home: Path | None = None) -> Path:
    home = home or Path.home()
    candidates = [
        home / "Library" / "Group Containers" / "group.com.apple.VoiceMemos.shared" / "Recordings",
        home
        / "Library"
        / "Containers"
        / "com.apple.VoiceMemos"
        / "Data"
        / "Library"
        / "Application Support"
        / "com.apple.voicememos"
        / "Recordings",
    ]
    return next((path for path in candidates if path.exists()), candidates[0])


def default_pi_bin(home: Path | None = None) -> str:
    """Locate the `pi` CLI portably: PATH first, then common install prefixes."""
    found = shutil.which("pi")
    if found:
        return found
    home = home or Path.home()
    candidates = (
        home / ".local" / "bin" / "pi",
        Path("/opt/homebrew/bin/pi"),  # Apple Silicon Homebrew
        Path("/usr/local/bin/pi"),  # Intel Homebrew
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return "pi"  # left bare so missing-install errors surface clearly


@dataclass(frozen=True)
class Settings:
    repo: Path
    recordings_dir: Path
    language: str
    whisper_model: str
    llm_provider: str
    llm_model: str
    pi_bin: str
    min_age_seconds: int
    scan_interval_seconds: int
    compile_timeout_seconds: int
    git_push: bool
    git_remote: str
    git_branch: str

    @classmethod
    def load(cls, repo: Path) -> Settings:
        repo = repo.expanduser().resolve()
        load_dotenv(repo / ".env")
        pi_bin = os.environ.get("XWIKI_PI_BIN") or default_pi_bin()
        return cls(
            repo=repo,
            recordings_dir=Path(
                os.environ.get("XWIKI_RECORDINGS_DIR", default_recordings_dir())
            ).expanduser(),
            language=os.environ.get("XWIKI_LANGUAGE", "zh"),
            whisper_model=os.environ.get(
                "XWIKI_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo"
            ),
            llm_provider=os.environ.get("XWIKI_LLM_PROVIDER", "iagent"),
            llm_model=os.environ.get("XWIKI_LLM_MODEL", "iagent/standard"),
            pi_bin=pi_bin,
            min_age_seconds=env_int("XWIKI_MIN_AGE_SECONDS", 60),
            scan_interval_seconds=env_int("XWIKI_SCAN_INTERVAL_SECONDS", 300, minimum=60),
            compile_timeout_seconds=env_int("XWIKI_COMPILE_TIMEOUT_SECONDS", 900, minimum=30),
            git_push=env_bool("XWIKI_GIT_PUSH", True),
            git_remote=os.environ.get("XWIKI_GIT_REMOTE", "origin"),
            git_branch=os.environ.get("XWIKI_GIT_BRANCH", "main"),
        )
