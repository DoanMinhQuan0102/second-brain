"""
Phần việc thật sự cần một model: thư mục/file không khớp luật nào ở rules.py.

Chỉ gửi TÊN — tên thư mục, tên vài file con, đuôi file — không bao giờ gửi
nội dung file. Dùng qwen3:14b qua Ollama local: đủ để đọc một danh sách tên
và đoán chủ đề, không cần vision, không cần viết mã, nên không cần tới
qwen3.6 (chậm hơn, dành cho ảnh) hay Gemini (free tier 20 request/ngày,
phí phạm cho việc dọn thư mục).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .rules import BUCKET_ARCHIVE, BUCKET_AUDIO, BUCKET_DOCUMENTS, BUCKET_PHOTOS, BUCKET_RESEARCH, Verdict

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MODEL = "qwen3:14b"
TIMEOUT_S = 120

_BUCKETS = {
    "photos": BUCKET_PHOTOS,
    "audio": BUCKET_AUDIO,
    "documents": BUCKET_DOCUMENTS,
    "research": BUCKET_RESEARCH,  # tên chủ đề do model đề xuất sẽ nối thêm sau
    "archive": BUCKET_ARCHIVE,
    "leave": None,
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "bucket": {"type": "string", "enum": list(_BUCKETS)},
        "topic_name": {"type": ["string", "null"],
                       "description": "chỉ điền nếu bucket=research: tên thư mục con gợi ý, ngắn gọn"},
        "reason": {"type": "string", "description": "một câu tiếng Việt giải thích"},
        "confidence": {"type": "string", "enum": ["cao", "vừa", "thấp"]},
    },
    "required": ["bucket", "reason", "confidence"],
}

_PROMPT = """Bạn đang giúp dọn một thư mục cá nhân (Second Brain). Dưới đây là
tên một mục (file hoặc thư mục) không khớp luật đơn giản nào. Dựa CHỈ vào tên
và danh sách tên file bên trong (nếu có) — không có nội dung — hãy đoán nó nên
xếp vào đâu:

  photos    — ảnh cá nhân
  audio     — ghi âm
  documents — tài liệu lẻ (hợp đồng, hóa đơn, sách...)
  research  — một đợt nghiên cứu người tiêu dùng/dự án (thường có ngày, tên
              thương hiệu, hoặc nhiều loại file trộn: excel+pptx+ảnh+ghi âm)
  archive   — thứ ít đụng tới (installer, bản cài, file nén cũ)
  leave     — để yên (trông như mã nguồn, cấu hình, hoặc không đủ manh mối)

Nếu không chắc, chọn "leave" và ghi rõ lý do — đừng đoán liều.

Mục cần phân loại:
{entry_desc}
"""


def classify_ambiguous(p: Path, sample_limit: int = 25) -> Verdict:
    """Gọi qwen3:14b để đoán một mục không khớp luật nào. Không đọc nội dung
    file — chỉ tên + (nếu là thư mục) danh sách tên con."""
    import requests

    if p.is_dir():
        names = sorted(x.name for x in p.iterdir())
        listing = "\n".join(f"  - {n}" for n in names[:sample_limit])
        if len(names) > sample_limit:
            listing += f"\n  ... và {len(names) - sample_limit} mục khác"
        entry_desc = f'Thư mục "{p.name}" ({len(names)} mục con):\n{listing}'
    else:
        size_kb = p.stat().st_size // 1024
        entry_desc = f'File "{p.name}" (đuôi {p.suffix or "(không có)"}, {size_kb} KB)'

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": _PROMPT.format(entry_desc=entry_desc)}],
        "format": _SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=TIMEOUT_S)
        r.raise_for_status()
        msg = r.json().get("message", {})
        text = (msg.get("content") or "").strip() or (msg.get("thinking") or "").strip()
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001 — model lỗi thì để yên, không chặn cả đợt scan
        return Verdict("leave", None, f"model local lỗi ({e}) — bỏ qua, để yên", source="llm")

    bucket_key = data.get("bucket", "leave")
    reason = data.get("reason", "").strip() or "model không giải thích"
    confidence = data.get("confidence", "thấp")
    reason = f"{reason} (model, độ tin: {confidence})"

    if bucket_key == "leave" or bucket_key not in _BUCKETS:
        return Verdict("leave", None, reason, source="llm")

    dest = _BUCKETS[bucket_key]
    if bucket_key == "research":
        topic = (data.get("topic_name") or p.name).strip()
        dest = f"{BUCKET_RESEARCH}/{topic}"

    # độ tin thấp → chỉ gắn cờ để người xem, không đề xuất di chuyển thẳng
    if confidence == "thấp":
        return Verdict("flag", None, reason, source="llm")

    return Verdict("move", dest, reason, source="llm")
