"""
Chunked extraction — N page images per Gemini request, verbatim Markdown out.

Why chunks and not the whole PDF in one request: 60 pages of dense
handwriting in a single response WILL truncate eventually, and a truncated
JSON is retried up to 5 times by extract_json — every retry a real request
against a 20/day cap. Small chunks make each request cheap to lose; the
store saves after every one, so a quota wall mid-document costs nothing.
Chunks keep pages consecutive so multi-page phiếu stay in one request, and
the quota ledger is consulted BEFORE each call — never burn an attempt we
already know will 429.
"""

from pathlib import Path

from second_brain import quota
from second_brain.llm import DEFAULT_MODEL, extract_json

from .pdf import page_count, prepare_pages
from .schema import LOCAL_STRICT_RULES, SCAN_PROMPT, SCAN_RESULT
from .store import ScanStore, doc_key, write_outputs

PAGES_PER_CALL = 6      # 2-page phiếu → 3 whole forms per request


# ═══════════════════════════════════════════════════════════════════════════════
# DRIVERS
# ═══════════════════════════════════════════════════════════════════════════════

def scan_target(
    target: Path,
    *,
    model: str = DEFAULT_MODEL,
    pages_spec: str | None = None,
    per_call: int = PAGES_PER_CALL,
    force: bool = False,
    max_calls: int | None = None,
    abort_after: int | None = 2,
    beside: bool = True,
) -> None:
    """One PDF, or every PDF under a folder (recursive)."""
    target = Path(target)
    if target.is_file():
        pdfs = [target]
    else:
        pdfs = sorted(p for p in target.rglob("*.pdf"))
        if pages_spec:
            print("⚠️ --pages chỉ áp dụng khi quét MỘT file — bỏ qua cho thư mục.")
            pages_spec = None
    if not pdfs:
        print(f"Không tìm thấy PDF nào trong {target}")
        return

    store = ScanStore()
    budget = {"calls": 0}
    for pdf in pdfs:
        scan_pdf(pdf, store, model=model, pages_spec=pages_spec,
                 per_call=per_call, force=force, budget=budget,
                 max_calls=max_calls, abort_after=abort_after, beside=beside)
        if max_calls is not None and budget["calls"] >= max_calls:
            break
    print(f"\n{store.summary()}")


def scan_pdf(pdf, store, *, model, pages_spec, per_call, force, budget,
             max_calls, abort_after, beside) -> None:
    local = model.startswith("ollama:")
    if local:
        per_call = 1                     # one image per request is qwen's happy path

    pdf = Path(pdf)
    n = page_count(pdf)
    selected = _parse_pages(pages_spec, n)
    rec = store.doc(doc_key(pdf), file=pdf, pages=n, model=model)
    if force:
        for p in selected:
            rec["page_md"].pop(str(p), None)

    todo = [p for p in selected if str(p) not in rec["page_md"]]
    if not todo:
        print(f"✅ {pdf.name}: {len(selected)} trang đã chép đủ — bỏ qua (--force để chép lại)")
        write_outputs(rec, store, beside=beside)
        store.save()
        return

    chunks = _chunk_consecutive(todo, per_call)
    print(f"📄 {pdf.name}: {n} trang, cần chép {len(todo)} → {len(chunks)} call · model {model}")
    if not local:
        print(f"   {quota.status(model)}")

    fails = 0
    for ci, chunk in enumerate(chunks, 1):
        if max_calls is not None and budget["calls"] >= max_calls:
            print(f"⏸️ Chạm giới hạn --limit {max_calls} call — dừng; chạy lại để chép tiếp.")
            break
        if not local and quota.remaining(model) <= 0:
            print(f"⛔ Hết quota {model} trong cửa sổ hôm nay — dừng; các trang còn lại "
                  f"tự vào lượt sau (fail-forward).")
            break

        label = f"{chunk[0]}-{chunk[-1]}" if len(chunk) > 1 else str(chunk[0])
        print(f"  [{ci}/{len(chunks)}] trang {label} ... ", end="", flush=True)
        try:
            images = prepare_pages(pdf, chunk)
            budget["calls"] += 1
            got = _extract(pdf.name, chunk, images, model)
            for p, md in got.items():
                rec["page_md"][str(p)] = md
            missing = [p for p in chunk if str(p) not in rec["page_md"]]
            if missing:
                rec["failed"][label] = f"model không trả trang {missing}"
                fails += 1
                print(f"⚠️ thiếu trang {missing}")
            else:
                rec["failed"].pop(label, None)
                fails = 0
                print(f"✅ {sum(len(rec['page_md'][str(p)]) for p in chunk):,} ký tự")
        except Exception as e:  # noqa: BLE001 — keep the batch going
            rec["failed"][label] = str(e)
            fails += 1
            print(f"❌ {e}")
            if abort_after and fails >= abort_after:
                print(f"⛔ {fails} lỗi liên tiếp — dừng; trang lỗi tự retry lần chạy sau.")
                write_outputs(rec, store, beside=beside)
                store.save()
                break
        write_outputs(rec, store, beside=beside)
        store.save()

    done = sum(1 for p in range(1, n + 1) if str(p) in rec["page_md"])
    print(f"   → {done}/{n} trang trong {rec.get('output')}")


# ═══════════════════════════════════════════════════════════════════════════════
# ONE CHUNK
# ═══════════════════════════════════════════════════════════════════════════════

def _extract(doc_name: str, chunk: list[int], images: list[Path], model: str) -> dict[int, str]:
    prompt = SCAN_PROMPT.format(doc_name=doc_name,
                                page_list=", ".join(str(p) for p in chunk))
    if model.startswith("ollama:"):
        from .local_llm import ollama_extract_json
        raw = ollama_extract_json(prompt + LOCAL_STRICT_RULES, images[0],
                                  SCAN_RESULT, model.split(":", 1)[1])
    else:
        # max_retries=3, not the repo default 5: every attempt is billed against
        # RPD, so a persistently failing chunk must cost at most 3 requests.
        raw = extract_json(prompt, images=images, schema=SCAN_RESULT, model=model,
                           max_retries=3)

    items = [it for it in (raw.get("pages") or [])
             if isinstance(it, dict) and (it.get("markdown") or "").strip()]
    out: dict[int, str] = {}
    returned = [it.get("page") for it in items]
    if sorted(p for p in returned if isinstance(p, int)) != sorted(chunk) \
            and len(items) == len(chunk):
        # Model renumbered from 1 — images were sent in chunk order, map back.
        for p, it in zip(chunk, items):
            out[p] = it["markdown"].strip()
        return out
    for it in items:
        if it.get("page") in chunk:
            out[it["page"]] = it["markdown"].strip()
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_pages(spec: str | None, n: int) -> list[int]:
    """'1-6,9' → [1,2,3,4,5,6,9]; None → all pages."""
    if not spec:
        return list(range(1, n + 1))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            pages.update(range(int(a), int(b) + 1))
        elif part:
            pages.add(int(part))
    bad = [p for p in pages if not 1 <= p <= n]
    if bad:
        raise SystemExit(f"--pages {spec}: trang {bad} nằm ngoài 1..{n}")
    return sorted(pages)


def _chunk_consecutive(pages: list[int], k: int) -> list[list[int]]:
    """Split into runs of consecutive pages, each at most k long — a gap
    (already-done page in the middle) starts a new chunk so every request
    stays a contiguous stretch of paper."""
    chunks: list[list[int]] = []
    run: list[int] = []
    for p in pages:
        if run and (p != run[-1] + 1 or len(run) >= k):
            chunks.append(run)
            run = []
        run.append(p)
    if run:
        chunks.append(run)
    return chunks
