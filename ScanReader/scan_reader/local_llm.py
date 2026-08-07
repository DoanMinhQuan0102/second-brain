"""
Local backend — Ollama on this laptop, zero cloud, zero quota.

Use by prefixing the model with "ollama:", e.g.
    python -m scan_reader scan file.pdf --model ollama:qwen3.6

Same wire contract as PhotoRecall's local_llm, but standalone: the strict
rules appended there are photo rules; a dictation task needs its own (they
are added by the caller in extract.py). num_ctx is bigger than the photo
task's 8192 — a dense A4 of handwriting is a lot more output tokens than a
caption record.
"""

import base64
import copy
import json
import os
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

# First call loads a 20+ GB model from disk — give it room to breathe.
TIMEOUT_S = 1800


def ollama_extract_json(prompt: str, image: Path, schema: dict, model: str) -> dict:
    """Same contract as second_brain.llm.extract_json, served from localhost."""
    import requests

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [base64.b64encode(Path(image).read_bytes()).decode()],
        }],
        "format": _to_json_schema(schema),
        "stream": False,
        "think": False,              # dictation-grade task; thinking just burns minutes
        "options": {"temperature": 0.1, "num_ctx": 12288},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=TIMEOUT_S)
        r.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            "Không kết nối được Ollama. Mở app Ollama hoặc chạy `ollama serve` rồi thử lại."
        ) from e
    msg = r.json().get("message", {})
    # Some models (qwen3-vl with think:false) misroute their output into the
    # `thinking` field and leave `content` empty — take whichever holds JSON.
    text = (msg.get("content") or "").strip() or (msg.get("thinking") or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Ollama ({model}) không trả JSON hợp lệ: {text[:120]!r}") from e


def _to_json_schema(schema: dict) -> dict:
    """Gemini-style schema → standard JSON Schema (Ollama's format field)."""
    out = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.pop("nullable", False) and isinstance(node.get("type"), str):
                node["type"] = [node["type"], "null"]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)
    return out
