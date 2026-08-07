"""
Store — processed/scan_reader.json + assembled Markdown per document.

Same discipline as the other branches (atomic writes, failed map, retry next
run) with one twist: the unit of work is a PAGE, so the record keeps
`page_md` per page and the .md files are REBUILT after every saved chunk —
an interrupted or quota-walled run leaves a readable, partially-filled
document instead of nothing. Two copies of the .md: the canonical one in
vault/processed/scanreader/, plus one right beside the source PDF, because
that is where the owner's project folders (rawdata + merged transcripts)
already collect their Claude-ready text.
"""

from datetime import datetime
from pathlib import Path

from second_brain import config
from second_brain.store import _read_json, _write_atomic

STORE_FILE = config.PROCESSED_DIR / "scan_reader.json"
OUTPUT_DIR = config.PROCESSED_DIR / "scanreader"
SCHEMA_VERSION = "1.0"

LEGEND = ("Quy ước: **đậm** = chữ viết tay · ☑/☐ = ô tick · `(khoanh)` = "
          "khoanh tròn · `~~chữ~~` = bị gạch xóa · `(?)` = ký tự không chắc · "
          "`[không đọc được]` · `(bỏ trống)` = mục không được điền")


def doc_key(path: Path) -> str:
    """Stable id: path relative to the Drive root, forward slashes."""
    p = Path(path).resolve()
    try:
        return p.relative_to(config.DRIVE_ROOT.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


class ScanStore:
    def __init__(self, store_file: Path | None = None):
        self.path = Path(store_file or STORE_FILE)
        self.db = _read_json(self.path, self._empty())
        self.db.setdefault("docs", {})

    @staticmethod
    def _empty() -> dict:
        return {
            "meta": {"created": datetime.now().isoformat(), "version": SCHEMA_VERSION},
            "docs": {},    # key → document record
        }

    def save(self) -> None:
        self.db.setdefault("meta", {})["last_updated"] = datetime.now().isoformat()
        _write_atomic(self.path, self.db)

    # ── Reads ─────────────────────────────────────────────────────────────────

    def docs(self) -> list[dict]:
        items = list(self.db["docs"].values())
        items.sort(key=lambda r: r.get("updated_at") or r.get("created_at") or "",
                   reverse=True)
        return items

    def find(self, needle: str) -> dict | None:
        """Look a document up by key substring or file stem, newest first."""
        needle = needle.lower()
        for rec in self.docs():
            if needle in rec["key"].lower() or needle in Path(rec["file"]).stem.lower():
                return rec
        return None

    # ── Writes ────────────────────────────────────────────────────────────────

    def doc(self, key: str, *, file: Path, pages: int, model: str) -> dict:
        rec = self.db["docs"].get(key)
        if rec is None:
            rec = {"key": key, "file": str(file),
                   "created_at": datetime.now().isoformat(),
                   "page_md": {}, "failed": {}}
            self.db["docs"][key] = rec
        rec.update(pages=pages, model=model,
                   updated_at=datetime.now().isoformat())
        return rec

    def summary(self) -> str:
        total = sum(len(r["page_md"]) for r in self.db["docs"].values())
        return (f"{len(self.db['docs'])} tài liệu · {total} trang đã chép"
                f" → {self.path}")


# ═══════════════════════════════════════════════════════════════════════════════
# MARKDOWN ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

def output_path(rec: dict, store: ScanStore) -> Path:
    if rec.get("output"):
        return Path(rec["output"])
    stem = Path(rec["file"]).stem
    taken = {r.get("output") for r in store.db["docs"].values() if r is not rec}
    cand = OUTPUT_DIR / f"{stem}.md"
    if str(cand) in taken:                      # two PDFs, same stem
        import hashlib
        cand = OUTPUT_DIR / f"{stem}_{hashlib.sha1(rec['key'].encode()).hexdigest()[:6]}.md"
    rec["output"] = str(cand)
    return cand


def build_markdown(rec: dict) -> str:
    n = rec.get("pages", 0)
    done = sum(1 for p in range(1, n + 1) if str(p) in rec["page_md"])
    head = [
        f"# {Path(rec['file']).stem} — trích xuất từ bản scan",
        "",
        f"> Nguồn: `{rec['file']}` · {n} trang · model `{rec.get('model', '?')}` · "
        f"cập nhật {datetime.now().strftime('%Y-%m-%d %H:%M')} · đã chép {done}/{n} trang",
        f"> {LEGEND}",
        "",
    ]
    body = []
    for p in range(1, n + 1):
        body.append("---")
        body.append("")
        body.append(f"## Trang {p}")
        body.append("")
        md = rec["page_md"].get(str(p))
        body.append(md if md else
                    "*(chưa trích xuất được — chạy lại `python -m scan_reader scan` để bổ sung)*")
        body.append("")
    return "\n".join(head + body)


def write_outputs(rec: dict, store: ScanStore, *, beside: bool = True) -> Path:
    """Rebuild the .md from page_md — called after every saved chunk."""
    out = output_path(rec, store)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = build_markdown(rec)
    out.write_text(text, encoding="utf-8")
    if beside:
        try:
            Path(rec["file"]).with_suffix(".md").write_text(text, encoding="utf-8")
        except OSError as e:                    # source dir read-only → vault copy still stands
            print(f"  (không ghi được bản .md cạnh file gốc: {e})")
    return out
