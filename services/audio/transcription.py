import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

WHISPER_MODE = os.getenv("WHISPER_MODE", "openai").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_whisper_module = None


def transcribe_audio(file_path: Path) -> str:
    if WHISPER_MODE == "local":
        return _transcribe_local(file_path)
    return _transcribe_openai(file_path)


def _transcribe_openai(file_path: Path) -> str:
    if not OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY is required for Whisper transcription.")
    client = OpenAI(api_key=OPENAI_API_KEY)
    with file_path.open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=os.getenv("WHISPER_MODEL", "whisper-1"),
            file=audio_file,
        )
    return transcription.text.strip()


def _transcribe_local(file_path: Path) -> str:
    whisper = _ensure_whisper()
    model_name = os.getenv("WHISPER_LOCAL_MODEL", "base")
    model = whisper.load_model(model_name)
    result = model.transcribe(str(file_path))
    return result.get("text", "").strip()


def _ensure_whisper():
    global _whisper_module
    if _whisper_module is not None:
        return _whisper_module
    try:
        import whisper  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "whisper package is not installed. Run `pip install -r requirements.txt`."
        ) from exc
    _whisper_module = whisper
    return whisper

