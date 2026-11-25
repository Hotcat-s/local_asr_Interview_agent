"""API smoke tests using a fake engine (no model loading)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from core.progress import STAGE_ASR, STAGE_DONE, STAGE_QA, emit
from core.schemas import InterviewReport, QAAnalysis, QAPair, Transcript, TranscriptSegment

from backend.app import create_app


class FakeEngine:
    def transcribe(self, audio_path, progress=None, chunk_seconds=None):
        emit(progress, STAGE_ASR, 1, 1, "识别完成")
        return Transcript(
            segments=[
                TranscriptSegment(0.0, 1.0, "请介绍一下你自己", "面试官"),
                TranscriptSegment(1.0, 4.0, "我有五年后端经验", "候选人"),
            ],
            duration=4.0,
            language="zh",
        )

    def build_qa(self, transcript, progress=None):
        emit(progress, STAGE_QA, 1, 1, "问答对完成")
        return [
            QAPair(
                index=0,
                question="请介绍一下你自己",
                answer="我有五年后端经验",
                question_speaker="面试官",
                answer_speaker="候选人",
                start=0.0,
                end=4.0,
            )
        ]

    def analyze(self, qa_pairs, llm_config=None, progress=None, analysis_config=None):
        emit(progress, STAGE_DONE, 1, 1, "分析完成")
        return InterviewReport(
            overall_score=88.0,
            summary="整体表现不错",
            items=[
                QAAnalysis(
                    index=0,
                    question="请介绍一下你自己",
                    answer="我有五年后端经验",
                    score=88.0,
                    strengths=["经验匹配"],
                    weaknesses=["细节不足"],
                    reference_answer="结构化介绍经历",
                    suggestion="补充量化结果",
                )
            ],
            improvements=["补充项目数据"],
        )

    def unload(self):
        pass


@pytest.fixture()
def api(tmp_path):
    app = create_app(str(tmp_path))
    state = app.state.interview
    state.set_engine(FakeEngine())
    with TestClient(app) as client:
        yield client, tmp_path


def wait_for_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_health(api):
    client, _ = api
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_full_pipeline(api):
    client, tmp_path = api
    audio = tmp_path / "meeting.wav"
    audio.write_bytes(b"RIFF")

    imported = client.post("/api/recordings/import", json={"path": str(audio)})
    assert imported.status_code == 200
    recording_id = imported.json()["recording"]["id"]
    assert imported.json()["recording"]["status"] == "imported"

    job = client.post(f"/api/recordings/{recording_id}/transcribe").json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"

    detail = client.get(f"/api/recordings/{recording_id}").json()
    assert detail["recording"]["status"] == "transcribed"
    assert len(detail["transcript"]["segments"]) == 2
    assert len(detail["qa_pairs"]) == 1

    job = client.post(f"/api/recordings/{recording_id}/analyze").json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"

    detail = client.get(f"/api/recordings/{recording_id}").json()
    assert detail["recording"]["status"] == "analyzed"
    assert detail["report"]["overall_score"] == 88.0

    listed = client.get("/api/recordings").json()["recordings"]
    assert [item["id"] for item in listed] == [recording_id]


def test_edit_transcript_rebuilds_qa(api):
    client, tmp_path = api
    audio = tmp_path / "meeting.wav"
    audio.write_bytes(b"RIFF")
    recording_id = client.post(
        "/api/recordings/import", json={"path": str(audio)}
    ).json()["recording"]["id"]

    response = client.put(
        f"/api/recordings/{recording_id}/transcript",
        json={
            "segments": [
                {"start": 0, "end": 2, "text": "问题", "speaker": "面试官"},
                {"start": 2, "end": 5, "text": "回答", "speaker": "候选人"},
            ],
            "regenerate_qa": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["recording"]["status"] == "transcribed"
    assert len(response.json()["qa_pairs"]) == 1


def test_settings_roundtrip(api):
    client, _ = api
    response = client.put("/api/settings", json={"chunk_seconds": 120})
    assert response.status_code == 200
    assert response.json()["chunk_seconds"] == 120
    assert client.get("/api/settings").json()["chunk_seconds"] == 120


def test_delete_recording(api):
    client, tmp_path = api
    audio = tmp_path / "meeting.wav"
    audio.write_bytes(b"RIFF")
    recording_id = client.post(
        "/api/recordings/import", json={"path": str(audio)}
    ).json()["recording"]["id"]

    assert client.delete(f"/api/recordings/{recording_id}").status_code == 204
    assert client.get(f"/api/recordings/{recording_id}").status_code == 404
