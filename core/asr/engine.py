"""Thin wrapper around :class:`funasr.AutoModel`.

The ``funasr`` / ``torch`` imports happen inside :meth:`FunASREngine.load` so
that merely importing :mod:`core.engine` stays lightweight.

Chunked transcription
---------------------
FunASR exposes no incremental progress callback, so long recordings are sliced
into ``chunk_seconds`` pieces (default 300 s), transcribed one piece at a time
and merged.  Emitting progress after every piece gives the UI a perceptible
``STAGE_ASR`` progress bar instead of a single 0→100 jump.

Speaker labels produced by FunASR are only meaningful *within one generate
call*.  Cross-chunk alignment therefore uses a simple, documented heuristic:
the first speaker of a new chunk is assumed to continue the last speaker of the
previous chunk, and the remaining local labels are mapped to already-known
global labels in first-appearance order (new labels are appended when a chunk
introduces more speakers than seen before).  This is reliable for the typical
alternating two-person interview but can mislabel speakers when a chunk boundary
coincides exactly with a speaker change; such cases are logged as warnings.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from core.config import ModelConfig
from core.exceptions import CancelledError, TranscriptionError
from core.models.manager import ModelManager
from core.progress import (
    STAGE_ASR,
    STAGE_DIARIZE,
    STAGE_MODEL,
    ProgressCallback,
    emit,
)
from core.schemas import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SECONDS = 300
_TARGET_SAMPLE_RATE = 16000


class _SpeakerAligner:
    """Map per-chunk local speaker labels onto stable global labels.

    See the module docstring for the heuristic and its limitations.
    """

    def __init__(self) -> None:
        self._known: list[str] = []
        self._prev_last: str | None = None

    def align(self, local_labels: list[str], first_chunk: bool) -> dict[str, str]:
        order: list[str] = []
        for label in local_labels:
            if label not in order:
                order.append(label)

        if not first_chunk and len(order) > len(self._known):
            logger.warning(
                "Chunk exposes %d speakers but only %d are known; "
                "cross-chunk speaker labels may be unreliable",
                len(order),
                len(self._known),
            )

        mapping: dict[str, str] = {}
        used: set[str] = set()

        # Continuation seeding: the first speaker likely carries over the
        # boundary from the previous chunk.
        if not first_chunk and self._prev_last is not None and order:
            mapping[order[0]] = self._prev_last
            used.add(self._prev_last)

        for label in order:
            if label in mapping:
                continue
            for global_label in self._known:
                if global_label not in used:
                    mapping[label] = global_label
                    used.add(global_label)
                    break
            else:
                global_label = f"SPK{len(self._known)}"
                self._known.append(global_label)
                mapping[label] = global_label
                used.add(global_label)

        if first_chunk:
            self._known = [mapping[label] for label in order]
        if local_labels:
            self._prev_last = mapping[local_labels[-1]]
        return mapping


class FunASREngine:
    """Run a combined VAD + ASR + punctuation + speaker pipeline."""

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        model_manager: ModelManager | None = None,
    ) -> None:
        self.model_config = model_config or ModelConfig()
        self.model_manager = model_manager or ModelManager()
        self._model = None
        self._device = "cpu"

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _resolve_paths(self) -> dict[str, str]:
        cfg = self.model_config
        paths = self.model_manager.all_paths()
        return {
            "asr": cfg.asr or paths["asr"],
            "vad": cfg.vad or paths["vad"],
            "punc": cfg.punc or paths["punc"],
            "spk": cfg.spk or paths["spk"],
        }

    def load(self, progress: ProgressCallback | None = None) -> None:
        if self._model is not None:
            return

        emit(progress, STAGE_MODEL, 0, 1, "加载本地 ASR 模型…", "首次加载可能较慢")
        try:
            import torch  # noqa: PLC0415 - heavy import kept lazy
            from funasr import AutoModel  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - environment guard
            raise TranscriptionError(f"FunASR/torch unavailable: {exc}") from exc

        paths = self._resolve_paths()
        device = self.model_config.device
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but unavailable; falling back to CPU")
            device = "cpu"
        self._device = device

        logger.info(
            "Loading FunASR models (device=%s): asr=%s vad=%s punc=%s spk=%s",
            device,
            paths["asr"],
            paths["vad"],
            paths["punc"],
            paths["spk"],
        )
        try:
            self._model = AutoModel(
                model=paths["asr"],
                vad_model=paths["vad"],
                punc_model=paths["punc"],
                spk_model=paths["spk"],
                device=device,
                disable_pbar=True,
                disable_update=True,
            )
        except Exception as exc:  # pragma: no cover - heavy, environment dependent
            self._model = None
            raise TranscriptionError(f"Failed to load FunASR models: {exc}") from exc
        emit(progress, STAGE_MODEL, 1, 1, "模型加载完成")

    def unload(self) -> None:
        self._model = None
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # pragma: no cover - best effort
            pass

    # ------------------------------------------------------------------ public API

    def transcribe(
        self,
        audio_path: str,
        progress: ProgressCallback | None = None,
        chunk_seconds: int = DEFAULT_CHUNK_SECONDS,
    ) -> Transcript:
        """Transcribe ``audio_path``, slicing long audio for visible progress."""

        self.load(progress)
        assert self._model is not None

        duration = self._probe_duration(audio_path)
        use_chunks = chunk_seconds and chunk_seconds > 0 and duration > chunk_seconds
        if use_chunks:
            return self._transcribe_chunked(audio_path, duration, int(chunk_seconds), progress)
        return self._transcribe_single(audio_path, duration, progress)

    # ------------------------------------------------------------------ single pass

    def _transcribe_single(
        self,
        audio_path: str,
        duration: float,
        progress: ProgressCallback | None,
    ) -> Transcript:
        emit(progress, STAGE_ASR, 0, 1, "转写中（VAD + ASR + 标点 + 说话人）…")
        segments, raw_text = self._generate(audio_path)
        emit(
            progress,
            STAGE_ASR,
            1,
            1,
            f"转写完成，共 {len(segments)} 段",
            f"共 {len(segments)} 段",
        )
        return self._build_transcript(segments, raw_text, duration)

    # ----------------------------------------------------------------- chunked pass

    def _transcribe_chunked(
        self,
        audio_path: str,
        duration: float,
        chunk_seconds: int,
        progress: ProgressCallback | None,
    ) -> Transcript:
        import math

        total_chunks = max(1, int(math.ceil(duration / chunk_seconds)))
        logger.info("Transcribing %.0fs audio in %d chunks", duration, total_chunks)

        waveform, sample_rate = self._load_waveform(audio_path)
        aligner = _SpeakerAligner()
        merged: list[TranscriptSegment] = []
        raw_parts: list[str] = []

        with tempfile.TemporaryDirectory(prefix="interview_chunks_") as tmp:
            for index in range(total_chunks):
                start_s = index * chunk_seconds
                end_s = min(duration, start_s + chunk_seconds)
                start_sample = int(start_s * sample_rate)
                end_sample = int(end_s * sample_rate)
                piece = waveform[start_sample:end_sample]
                if piece.size == 0:
                    emit(
                        progress,
                        STAGE_ASR,
                        index + 1,
                        total_chunks,
                        f"转写中（第 {index + 1}/{total_chunks} 片）…",
                        f"已处理 {end_s:.0f}/{duration:.0f} 秒",
                    )
                    continue

                chunk_path = str(Path(tmp) / f"chunk_{index:04d}.wav")
                self._write_wave(piece, sample_rate, chunk_path)

                local_segments, raw_text = self._generate(chunk_path)
                mapping = aligner.align(
                    [segment.speaker for segment in local_segments],
                    first_chunk=index == 0,
                )
                for segment in local_segments:
                    merged.append(
                        TranscriptSegment(
                            start=segment.start + start_s,
                            end=segment.end + start_s,
                            text=segment.text,
                            speaker=mapping.get(segment.speaker, segment.speaker),
                        )
                    )
                if raw_text:
                    raw_parts.append(raw_text)

                emit(
                    progress,
                    STAGE_ASR,
                    index + 1,
                    total_chunks,
                    f"转写中（第 {index + 1}/{total_chunks} 片）…",
                    f"已处理 {end_s:.0f}/{duration:.0f} 秒",
                )

        emit(progress, STAGE_DIARIZE, 1, 1, "合并说话人片段…", f"共 {len(merged)} 段")
        return self._build_transcript(merged, " ".join(raw_parts), duration)

    # --------------------------------------------------------------------- internals

    def _generate(self, audio_path: str) -> tuple[list[TranscriptSegment], str]:
        assert self._model is not None
        try:
            result = self._model.generate(
                input=audio_path,
                sentence_timestamp=True,
                return_spk_res=True,
                batch_size_s=300,
            )
        except CancelledError:
            raise
        except Exception as exc:
            raise TranscriptionError(f"Transcription failed: {exc}") from exc

        if not result:
            raise TranscriptionError("FunASR returned an empty result")
        first = result[0]
        return self._parse_segments(first), str(first.get("text", ""))

    @staticmethod
    def _build_transcript(
        segments: list[TranscriptSegment],
        raw_text: str,
        duration: float,
    ) -> Transcript:
        final_duration = duration or (segments[-1].end if segments else 0.0)
        return Transcript(
            segments=segments,
            duration=final_duration,
            language="zh",
            raw_text=raw_text,
        )

    @staticmethod
    def _probe_duration(audio_path: str) -> float:
        try:
            import soundfile as sf  # noqa: PLC0415

            return float(sf.info(audio_path).duration)
        except Exception:  # noqa: BLE001 - fall back to full decode
            pass
        try:
            import librosa  # noqa: PLC0415

            return float(librosa.get_duration(path=audio_path))
        except Exception:  # noqa: BLE001 - unable to probe
            return 0.0

    @staticmethod
    def _load_waveform(audio_path: str):
        try:
            import librosa  # noqa: PLC0415
            import numpy as np  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - environment guard
            raise TranscriptionError(f"Audio libraries unavailable: {exc}") from exc
        waveform, sample_rate = librosa.load(audio_path, sr=_TARGET_SAMPLE_RATE, mono=True)
        return np.asarray(waveform, dtype="float32"), sample_rate

    @staticmethod
    def _write_wave(piece, sample_rate: int, out_path: str) -> None:
        import soundfile as sf  # noqa: PLC0415

        sf.write(out_path, piece, sample_rate)

    @staticmethod
    def _parse_segments(result: dict) -> list[TranscriptSegment]:
        """Convert FunASR ``sentence_info`` (ms) into second-based segments."""

        sentence_info = result.get("sentence_info")
        segments: list[TranscriptSegment] = []
        if isinstance(sentence_info, list) and sentence_info:
            for item in sentence_info:
                text = str(item.get("text") or item.get("sentence") or "").strip()
                if not text:
                    continue
                start = float(item.get("start", 0.0)) / 1000.0
                end = float(item.get("end", 0.0)) / 1000.0
                spk = item.get("spk", 0)
                segments.append(
                    TranscriptSegment(
                        start=start,
                        end=end,
                        text=text,
                        speaker=_normalise_speaker(spk),
                    )
                )
        if segments:
            return segments

        # Fallback: no sentence/segment info, keep whole text as one utterance.
        text = str(result.get("text", "")).strip()
        if not text:
            return []
        timestamp = result.get("timestamp")
        end = 0.0
        if isinstance(timestamp, list) and timestamp:
            try:
                end = float(timestamp[-1][1]) / 1000.0
            except (TypeError, IndexError, ValueError):
                end = 0.0
        return [TranscriptSegment(start=0.0, end=end, text=text, speaker="SPK0")]


def _normalise_speaker(spk: object) -> str:
    """Return a stable ``SPK{n}`` label for a FunASR speaker id."""

    return f"SPK{spk}"
