#!/usr/bin/env python3
"""Install or remove the X-Wiki Voice Memos launchd agent."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from xwiki_config import Settings

LABEL = "com.xwiki.voice-ingest"
LEGACY_LABELS = ("com.1998x.x-wiki.voice-ingest",)


def launchctl(
    *arguments: str, check: bool = True, quiet: bool = False
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *arguments],
        check=check,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )


def provider_env_refs(
    settings: Settings, models_path: Path | None = None
) -> tuple[list[str], list[str]]:
    """Read ``models_path`` (default ~/.pi/agent/models.json) and return the
    env var names the configured provider references as ``$VAR`` placeholders,
    split into (present, missing).

    pi provider configs reference env vars as string placeholders such as
    ``{"apiKey": "$IAUTO_API_KEY"}``. These live only in the interactive
    session's environment, so without copying them into the launchd plist the
    nightly compile fails with "No API key found for <provider>".
    """
    refs: set[str] = set()
    models_path = models_path or Path.home() / ".pi" / "agent" / "models.json"
    try:
        data = json.loads(models_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    provider = data.get("providers", {}).get(settings.llm_provider, {})
    if not provider:
        return [], []

    def scan(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                scan(item)
        elif isinstance(value, list):
            for item in value:
                scan(item)
        elif isinstance(value, str) and value.startswith("$"):
            name = value[1:]
            if name:
                refs.add(name)

    scan(provider)
    present = sorted(name for name in refs if os.environ.get(name))
    missing = sorted(name for name in refs if not os.environ.get(name))
    return present, missing


def provider_credential_envs(
    settings: Settings, models_path: Path | None = None
) -> dict[str, str]:
    """Inherit launchd env vars that pi's configured LLM provider resolves at
    runtime from the parent shell so the headless agent can authenticate."""
    present, _missing = provider_env_refs(settings, models_path)
    return {name: os.environ[name] for name in present}


def missing_credential_envs(
    settings: Settings, models_path: Path | None = None
) -> list[str]:
    """Env var names the provider references but that are unset in the current
    session, so launchd would compile without a key."""
    _present, missing = provider_env_refs(settings, models_path)
    return missing



def build_payload(settings: Settings, python: Path) -> dict:
    logs = settings.repo / ".state" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    resolved_pi = shutil.which(settings.pi_bin) or settings.pi_bin
    path_parts = [
        str(Path(resolved_pi).expanduser().parent),
        str(python.parent),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    environment = {
        "HOME": str(Path.home()),
        "PATH": ":".join(dict.fromkeys(path_parts)),
        "PYTHONUNBUFFERED": "1",
        "XWIKI_LANGUAGE": settings.language,
        "XWIKI_WHISPER_MODEL": settings.whisper_model,
        "XWIKI_LLM_PROVIDER": settings.llm_provider,
        "XWIKI_LLM_MODEL": settings.llm_model,
        "XWIKI_PI_BIN": resolved_pi,
        "XWIKI_RECORDINGS_DIR": str(settings.recordings_dir),
        "XWIKI_MIN_AGE_SECONDS": str(settings.min_age_seconds),
        "XWIKI_COMPILE_TIMEOUT_SECONDS": str(settings.compile_timeout_seconds),
        "XWIKI_GIT_PUSH": "true" if settings.git_push else "false",
        "XWIKI_GIT_REMOTE": settings.git_remote,
        "XWIKI_GIT_BRANCH": settings.git_branch,
    }
    environment.update(provider_credential_envs(settings))
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(settings.repo / "scripts" / "process_voice_memos.py"),
            "--repo",
            str(settings.repo),
        ],
        "WorkingDirectory": str(settings.repo),
        "WatchPaths": [str(settings.recordings_dir)],
        "StartInterval": settings.scan_interval_seconds,
        # StartInterval events are missed during sleep; this coalesced calendar
        # event gives launchd a recovery run after the Mac wakes.
        "StartCalendarInterval": {"Minute": 7},
        "ThrottleInterval": 30,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "AbandonProcessGroup": False,
        "StandardOutPath": str(logs / "launchd.out.log"),
        "StandardErrorPath": str(logs / "launchd.err.log"),
        "EnvironmentVariables": environment,
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    settings = Settings.load(repo)
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--no-start", action="store_true")
    args = parser.parse_args()

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    launchctl("bootout", domain, str(plist_path), check=False, quiet=True)
    for legacy_label in LEGACY_LABELS:
        legacy_path = launch_agents / f"{legacy_label}.plist"
        launchctl("bootout", domain, str(legacy_path), check=False, quiet=True)
        legacy_path.unlink(missing_ok=True)
    if args.remove:
        plist_path.unlink(missing_ok=True)
        print(f"Removed {LABEL}")
        return 0

    python = Path(sys.executable)
    if not (settings.repo / "scripts" / "process_voice_memos.py").is_file():
        parser.error(f"pipeline script not found under {settings.repo}")
    payload = build_payload(settings, python)
    plist_path.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML))
    # The plist now embeds LLM provider credentials; keep it owner-readable only.
    plist_path.chmod(0o600)
    missing = missing_credential_envs(settings)
    if missing:
        print(
            "Warning: launchd agent will not be able to compile the wiki; "
            f"provider {settings.llm_provider!r} references env vars that are "
            f"unset in the current session: {sorted(missing)}. "
            "Export them (or run `pi auth` to store credentials) and re-run "
            "install_launch_agent.py.",
            file=sys.stderr,
        )
    launchctl("bootstrap", domain, str(plist_path))
    launchctl("enable", service)
    if not args.no_start:
        launchctl("kickstart", "-k", service)
    print(plist_path)
    print(f"Full Disk Access executable: {Path(sys.executable).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
