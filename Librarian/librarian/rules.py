"""
Luật cứng — đoán trước bằng đuôi file / tên thư mục, không tốn một token nào.

Thứ tự áp luật: junk trước (rác thì đề xuất xóa, không hỏi model), rồi venv/
husk (thư mục kỹ thuật, luôn để người dùng tự quyết — không bao giờ tự động
xóa một venv, có thể rất to), rồi bucket theo đuôi file, rồi tên thư mục
research trông đã quen mặt. Cái gì không khớp luật nào rơi vào AMBIGUOUS —
đó là phần việc thật sự cần một model đọc hiểu (xem ollama_classify.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ── các bucket đích, tương đối so với gốc repo ────────────────────────────────
BUCKET_PHOTOS    = "vault/raw/photos/inbox"
BUCKET_AUDIO     = "vault/raw/audio"
BUCKET_DOCUMENTS = "vault/raw/documents"
BUCKET_RESEARCH  = "vault/raw/research"
BUCKET_ARCHIVE   = "_archive"

# ── rác: luôn đề xuất xóa, không bao giờ cần hỏi model ───────────────────────
JUNK_DIR_NAMES  = {"__pycache__", ".ipynb_checkpoints", ".pytest_cache", ".mypy_cache"}
JUNK_FILE_NAMES = {"Thumbs.db", ".DS_Store"}
JUNK_FILE_SUFFIXES = (".pyc", ".pyo", ".tmp", ".bak", "~")

# ── đuôi file → bucket (chỉ áp cho FILE nằm lẻ, không phải cả một thư mục) ───
EXT_BUCKETS = {
    ".jpg": BUCKET_PHOTOS, ".jpeg": BUCKET_PHOTOS, ".png": BUCKET_PHOTOS,
    ".heic": BUCKET_PHOTOS, ".webp": BUCKET_PHOTOS,
    ".m4a": BUCKET_AUDIO, ".mp3": BUCKET_AUDIO, ".wav": BUCKET_AUDIO,
    ".pdf": BUCKET_DOCUMENTS, ".docx": BUCKET_DOCUMENTS,
    ".xlsx": BUCKET_DOCUMENTS, ".pptx": BUCKET_DOCUMENTS,
}

# ── nhị phân cài đặt / lưu trữ → luôn về _archive ─────────────────────────────
INSTALLER_EXTS = {".exe", ".msi", ".msix"}
ARCHIVE_EXTS   = {".zip", ".7z", ".rar"}

# tên thư mục research trông quen: có ngày ở đầu, hoặc có [Tên] trong ngoặc
_RESEARCH_NAME_RE = re.compile(r"^\d{2,4}[.\-]\d{1,2}|\[[^\]]+\]")


@dataclass
class Verdict:
    action: str            # "move" | "delete" | "flag" | "leave" | "ambiguous"
    dest: str | None        # đường dẫn đích tương đối, nếu action == "move"
    reason: str            # lý do, tiếng Việt, một dòng
    source: str = "rule"   # "rule" | "llm"


def _is_junk(p: Path) -> bool:
    if p.is_dir():
        return p.name in JUNK_DIR_NAMES
    if p.name in JUNK_FILE_NAMES:
        return True
    return p.name.endswith(JUNK_FILE_SUFFIXES)


def _is_venv(p: Path) -> bool:
    if not p.is_dir():
        return False
    if (p / "pyvenv.cfg").exists():
        return True
    # site-packages thường nằm sâu 2-3 cấp (lib/pythonX.Y/site-packages)
    return any(p.rglob("pyvenv.cfg"))


def _is_pycache_husk(p: Path) -> bool:
    """Thư mục chỉ còn __pycache__/*.pyc, không còn .py nguồn nào — dấu hiệu
    source đã bị xóa/di dời (từng xảy ra với ResearchAnalyst/ScanReader khi
    source thật nằm trên một nhánh git khác)."""
    if not p.is_dir():
        return False
    has_py = any(p.rglob("*.py"))
    has_pyc = any(p.rglob("*.pyc"))
    return has_pyc and not has_py


def _looks_like_research_topic(p: Path) -> bool:
    return p.is_dir() and bool(_RESEARCH_NAME_RE.match(p.name))


def _has_git_dir(p: Path) -> bool:
    return p.is_dir() and (p / ".git").exists()


def classify_entry(p: Path) -> Verdict:
    if _is_junk(p):
        return Verdict("delete", None, "rác biết mặt (bytecode/cache/temp) — xóa an toàn")

    if _is_venv(p):
        return Verdict("flag", None,
                        "trông như một virtualenv/site-packages — có thể rất to, "
                        "tự quyết định giữ hay xóa, Librarian không tự động đụng vào")

    if _has_git_dir(p):
        return Verdict("flag", None,
                        "có .git riêng bên trong — có thể là mã nguồn/clone ngoài, xem trước khi động")

    if _is_pycache_husk(p):
        return Verdict("flag", None,
                        "chỉ còn bytecode, không còn source .py — kiểm tra xem source có "
                        "đang nằm trên nhánh git khác trước khi xóa")

    if p.is_file():
        ext = p.suffix.lower()
        if ext in INSTALLER_EXTS or ext in ARCHIVE_EXTS:
            return Verdict("move", BUCKET_ARCHIVE, f"file cài đặt/nén ({ext}) — dồn về _archive")
        if ext in EXT_BUCKETS:
            bucket = EXT_BUCKETS[ext]
            return Verdict("move", bucket, f"file lẻ đuôi {ext} — xếp vào {bucket}")
        return Verdict("ambiguous", None, "file không rõ loại")

    # thư mục
    if _looks_like_research_topic(p):
        return Verdict("move", f"{BUCKET_RESEARCH}/{p.name}",
                        "tên có ngày/[Chủ đề] — trông như một đợt research")

    return Verdict("ambiguous", None, "thư mục không khớp luật nào")


def sweep_junk(root: Path, skip_dirnames: set[str] = frozenset({"vault", ".git"})) -> list[Path]:
    """Quét đệ quy tìm rác (pycache/tmp/...), bỏ qua các thư mục lớn không cần dòm
    (mặc định bỏ qua vault/ — 26k+ file, .git/)."""
    found: list[Path] = []
    for p in root.iterdir():
        if p.name in skip_dirnames:
            continue
        if _is_junk(p):
            found.append(p)
            continue
        if p.is_dir():
            for sub in p.rglob("*"):
                if sub.name in JUNK_DIR_NAMES or (sub.is_file() and _is_junk(sub)):
                    found.append(sub)

    # bỏ mục nào đã nằm trong một mục khác cũng sắp bị xóa (VD: .pyc bên
    # trong một __pycache__ cũng có mặt trong found) — xóa thư mục cha là đủ.
    found.sort(key=lambda p: len(p.parts))
    kept: list[Path] = []
    for p in found:
        if any(k in p.parents for k in kept):
            continue
        kept.append(p)
    return kept
