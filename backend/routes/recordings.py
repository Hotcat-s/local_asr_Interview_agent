"""Recording library, transcripts, Q/A pairs and pipeline triggers."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from core.schemas import QAPair, Transcript, TranscriptSegment
from core.status import RecordingStatus

from backend.deps import get_state
from backend.runtime import AppState
from backend.schemas import ImportRequest, QAPayload, RenameRequest, TranscriptPayload

router = APIRouter(prefix="/recordings", tags=["recordings"])

AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".webm", ".mp4", ".wma"}


@router.get("")
def list_recordings(
    status: str | None = None,
    search: str | None = None,
    state: AppState = Depends(get_state),
) -> dict:
    recordings = state.repo.list_recordings(status=status, search=search)
    return {"recordings": [asdict(item) for item in recordings]}


@router.post("/import")
def import_recording(payload: ImportRequest, state: AppState = Depends(get_state)) -> dict:
    source = Path(payload.path).expanduser()
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=400, detail="音频文件不存在")
    if source.suffix.lower() not in AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的音频格式：{source.suffix}")

    audio_path = _store_audio(source, state)
    title = (payload.title or source.stem).strip() or "未命名录音"
    recording_id = state.repo.create_recording(title, audio_path)
    return _detail(state, recording_id)


@router.post("/upload")
def upload_recording(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    state: AppState = Depends(get_state),
) -> dict:
    filename = Path(file.filename or "audio.wav")
    if filename.suffix.lower() not in AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的音频格式：{filename.suffix}")

    target = state.paths.audio_dir / f"{uuid.uuid4().hex}{filename.suffix.lower()}"
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    recording_title = (title or filename.stem).strip() or "未命名录音"
    recording_id = state.repo.create_recording(recording_title, str(target))
    return _detail(state, recording_id)


@router.get("/{recording_id}")
def get_recording(recording_id: int, state: AppState = Depends(get_state)) -> dict:
    return _detail(state, recording_id)


@router.patch("/{recording_id}")
def rename_recording(
    recording_id: int,
    payload: RenameRequest,
    state: AppState = Depends(get_state),
) -> dict:
    _require_recording(state, recording_id)
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    state.repo.rename_recording(recording_id, payload.title)
    return _detail(state, recording_id)


@router.delete("/{recording_id}", status_code=204)
def delete_recording(recording_id: int, state: AppState = Depends(get_state)) -> Response:
    recording = _require_recording(state, recording_id)
    state.repo.delete_recording(recording_id)
    _remove_managed_audio(recording.audio_path, state)
    return Response(status_code=204)


@router.post("/{recording_id}/transcribe")
def start_transcription(recording_id: int, state: AppState = Depends(get_state)) -> dict:
    _require_recording(state, recording_id)
    try:
        job = state.tasks.submit(recording_id, "transcribe")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.to_dict()


@router.post("/{recording_id}/analyze")
def start_analysis(recording_id: int, state: AppState = Depends(get_state)) -> dict:
    _require_recording(state, recording_id)
    if not state.repo.load_qa_pairs(recording_id):
        raise HTTPException(status_code=400, detail="没有可分析的问答对，请先完成转写")
    try:
        job = state.tasks.submit(recording_id, "analyze")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.to_dict()


@router.post("/{recording_id}/cancel")
def cancel_job(recording_id: int, state: AppState = Depends(get_state)) -> dict:
    _require_recording(state, recording_id)
    job = state.tasks.cancel_recording(recording_id)
    if job is None:
        raise HTTPException(status_code=404, detail="没有正在运行的任务")
    return job.to_dict()


@router.put("/{recording_id}/transcript")
def save_transcript(
    recording_id: int,
    payload: TranscriptPayload,
    state: AppState = Depends(get_state),
) -> dict:
    _require_recording(state, recording_id)
    segments = [
        TranscriptSegment(
            start=segment.start,
            end=segment.end,
            text=segment.text,
            speaker=segment.speaker,
        )
        for segment in payload.segments
    ]
    duration = payload.duration
    if duration is None:
        duration = segments[-1].end if segments else 0.0
    transcript = Transcript(
        segments=segments,
        duration=duration,
        language=payload.language,
        raw_text=" ".join(segment.text for segment in segments if segment.text),
    )
    state.repo.save_transcript(recording_id, transcript)

    if payload.regenerate_qa:
        qa_pairs = state.engine().build_qa(transcript)
        state.repo.save_qa_pairs(recording_id, qa_pairs)
    state.repo.update_status(recording_id, RecordingStatus.TRANSCRIBED.value)
    return _detail(state, recording_id)


@router.put("/{recording_id}/qa")
def save_qa(
    recording_id: int,
    payload: QAPayload,
    state: AppState = Depends(get_state),
) -> dict:
    _require_recording(state, recording_id)
    pairs = [
        QAPair(
            index=pair.index,
            question=pair.question,
            answer=pair.answer,
            question_speaker=pair.question_speaker,
            answer_speaker=pair.answer_speaker,
            start=pair.start,
            end=pair.end,
        )
        for pair in payload.pairs
    ]
    state.repo.save_qa_pairs(recording_id, pairs)
    return _detail(state, recording_id)


@router.post("/{recording_id}/qa/rebuild")
def rebuild_qa(recording_id: int, state: AppState = Depends(get_state)) -> dict:
    _require_recording(state, recording_id)
    transcript = state.repo.load_transcript(recording_id)
    if transcript is None or not transcript.segments:
        raise HTTPException(status_code=400, detail="还没有可用的转写文本")
    qa_pairs = state.engine().build_qa(transcript)
    state.repo.save_qa_pairs(recording_id, qa_pairs)
    return _detail(state, recording_id)


# --------------------------------------------------------------------- helpers


def _require_recording(state: AppState, recording_id: int):
    recording = state.repo.get_recording(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="录音不存在")
    return recording


def _detail(state: AppState, recording_id: int) -> dict:
    detail = state.repo.get_detail(recording_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="录音不存在")
    return asdict(detail)


def _store_audio(source: Path, state: AppState) -> str:
    source = source.resolve()
    try:
        source.relative_to(state.paths.audio_dir.resolve())
    except ValueError:
        target = state.paths.audio_dir / f"{uuid.uuid4().hex}{source.suffix.lower()}"
        shutil.copy2(source, target)
        return str(target)
    return str(source)


def _remove_managed_audio(audio_path: str, state: AppState) -> None:
    path = Path(audio_path)
    try:
        path.resolve().relative_to(state.paths.audio_dir.resolve())
    except ValueError:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
