"""Normalise arbitrary audio files to 16 kHz mono before ASR.

FunASR expects mono 16 kHz audio.  Rather than relying on the underlying
decoder chain we decode with ``soundfile``/``librosa`` and write a temporary
WAV so the model receives a predictable input.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.exceptions import AudioLoadError

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000


@dataclass
class AudioInfo:
    """Result of preparing an audio file.

    ``path`` points either at the original file (when it was already 16 kHz
    mono) or at a temporary converted WAV.  Callers must invoke
    :meth:`AudioLoader.cleanup` when finished with converted files.
    """

    path: str
    duration: float
    sample_rate: int
    converted: bool


class AudioLoader:
    """Decode and normalise audio files for the ASR engine."""

    def __init__(self, target_sample_rate: int = TARGET_SAMPLE_RATE) -> None:
        self.target_sample_rate = target_sample_rate
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def prepare(self, audio_path: str) -> AudioInfo:
        path = Path(audio_path).expanduser()
        if not path.exists():
            raise AudioLoadError(f"Audio file not found: {path}")

        try:
            import librosa  # noqa: PLC0415 - heavy optional import
            import soundfile as sf  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - environment guard
            raise AudioLoadError(f"Audio libraries unavailable: {exc}") from exc

        try:
            waveform, sample_rate = librosa.load(str(path), sr=self.target_sample_rate, mono=True)
        except Exception as exc:  # librosa raises a variety of errors
            raise AudioLoadError(f"Failed to decode {path}: {exc}") from exc

        import numpy as np  # noqa: PLC0415

        if waveform.size == 0:
            raise AudioLoadError(f"Audio file is empty: {path}")

        duration = float(len(waveform)) / float(sample_rate)

        # If the source was already the target format we can use it directly.
        if sample_rate == self.target_sample_rate and not path.suffix.lower() in {".mp3", ".m4a"}:
            try:
                info = sf.info(str(path))
                if info.samplerate == self.target_sample_rate and info.channels == 1:
                    return AudioInfo(str(path), duration, sample_rate, converted=False)
            except Exception:  # pragma: no cover - best effort only
                pass

        if self._temp_dir is None:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="interview_audio_")
        out_path = Path(self._temp_dir.name) / f"{path.stem}.wav"
        sf.write(str(out_path), np.asarray(waveform, dtype="float32"), self.target_sample_rate)
        logger.info("Converted %s to 16 kHz mono WAV at %s", path, out_path)
        return AudioInfo(str(out_path), duration, self.target_sample_rate, converted=True)

    def cleanup(self) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None
