"""Request payloads accepted by the sidecar API.

Responses are plain dictionaries produced from the core dataclasses, so this
module only needs to describe incoming data.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    path: str = Field(..., description="Absolute path to a local audio file")
    title: str | None = None


class RenameRequest(BaseModel):
    title: str


class SegmentPayload(BaseModel):
    start: float
    end: float
    text: str
    speaker: str = ""


class TranscriptPayload(BaseModel):
    segments: list[SegmentPayload] = Field(default_factory=list)
    duration: float | None = None
    language: str = "zh"
    regenerate_qa: bool = True


class QAPairPayload(BaseModel):
    index: int
    question: str
    answer: str
    question_speaker: str = ""
    answer_speaker: str = ""
    start: float = 0.0
    end: float = 0.0


class QAPayload(BaseModel):
    pairs: list[QAPairPayload] = Field(default_factory=list)


class LLMPayload(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float | None = None


class AnalysisPayload(BaseModel):
    batch_size: int | None = None
    max_chars_per_batch: int | None = None
    concurrency: int | None = None
    enable_summary: bool | None = None


class ModelsPayload(BaseModel):
    asr: str | None = None
    vad: str | None = None
    punc: str | None = None
    spk: str | None = None
    device: str | None = None


class SettingsPayload(BaseModel):
    models: ModelsPayload | None = None
    llm: LLMPayload | None = None
    analysis: AnalysisPayload | None = None
    chunk_seconds: int | None = None
    use_embedding_segmentation: bool | None = None


class TestLLMRequest(BaseModel):
    llm: LLMPayload | None = None
