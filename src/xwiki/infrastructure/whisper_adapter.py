"""Optional LOCAL mlx-whisper execution. Never resolve a remote HF model ID.

The adapter is imported only when a user explicitly invokes run-once. No
model download, network API, pi/LLM or Git operation is in this module.
"""

from __future__ import annotations

import hashlib
import platform
from pathlib import Path


class TranscriptionFailure(RuntimeError):
    code = "TRANSCRIBER_FAILED"
    retryable = True


class ModelUnavailable(TranscriptionFailure):
    code = "MODEL_NOT_FOUND"
    retryable = False


class PlatformUnavailable(TranscriptionFailure):
    code = "TRANSCRIBER_UNAVAILABLE"
    retryable = False


class InvalidTranscript(TranscriptionFailure):
    code = "INVALID_TRANSCRIPT"
    retryable = False


class LocalMLXWhisper:
    engine = "mlx-whisper"

    def __init__(self, model_dir: Path, *, language: str = "auto"):
        directory = Path(model_dir).expanduser().absolute()
        if directory.is_symlink() or not directory.is_dir():
            raise ModelUnavailable("use an already-installed local model directory")
        if language != "auto" and not (
            isinstance(language, str) and 2 <= len(language) <= 12
            and language.replace("-", "").isalpha()
        ):
            raise ValueError("invalid language code")
        self.model_dir = directory
        self.language = language
        self.model_key = hashlib.sha256(
            ("mlx-whisper/local/v1\0" + str(directory) + "\0" + language).encode()
        ).hexdigest()

    def transcribe(self, source_path: Path) -> str:
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise PlatformUnavailable("local mlx-whisper requires Apple Silicon macOS")
        try:
            import mlx_whisper  # noqa: PLC0415 - optional native dependency
        except ImportError as error:
            raise PlatformUnavailable("mlx_whisper is not installed") from error
        try:
            result = mlx_whisper.transcribe(
                str(source_path),
                path_or_hf_repo=str(self.model_dir),
                language=None if self.language == "auto" else self.language,
                task="transcribe",
                condition_on_previous_text=False,
                word_timestamps=False,
                verbose=False,
            )
        except OSError as error:
            raise TranscriptionFailure("local transcription failed") from error
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise InvalidTranscript("transcription did not return Unicode text")
        return result["text"]
