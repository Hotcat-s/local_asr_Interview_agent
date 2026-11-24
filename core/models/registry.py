"""Static registry mapping model roles to their on-disk relative paths.

Paths are relative to the ``core/models`` directory and match the layout that
ships with this repository.  They are intentionally data-only so the registry
can be inspected without touching the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass

MODELS_ROOT_RELPATH = "core/models"


@dataclass(frozen=True)
class ModelEntry:
    key: str
    name: str
    relative_path: str


MODEL_REGISTRY: dict[str, ModelEntry] = {
    "asr": ModelEntry(
        key="asr",
        name="Paraformer-zh (ASR + VAD + Punc)",
        relative_path=(
            "Paraformer-zh/"
            "speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
        ),
    ),
    "vad": ModelEntry(
        key="vad",
        name="FSMN-VAD",
        relative_path="fsmn-vad/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    ),
    "punc": ModelEntry(
        key="punc",
        name="CT-Transformer Punctuation",
        relative_path="ct-punc/punc_ct-transformer_cn-en-common-vocab471067-large",
    ),
    "spk": ModelEntry(
        key="spk",
        name="CAM++ Speaker Verification",
        relative_path="cam++/speech_campplus_sv_zh-cn_16k-common",
    ),
}

MODEL_KEYS: tuple[str, ...] = tuple(MODEL_REGISTRY.keys())
