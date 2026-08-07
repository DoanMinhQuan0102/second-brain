"""
CLI:
  python -m scan_reader scan   <file.pdf|thư mục> [--model M] [--pages 1-6,9]
                               [--pages-per-call N] [--limit N] [--force]
                               [--abort-after N] [--no-beside]
  python -m scan_reader pages  <file.pdf>     # soi cấu trúc PDF — 0 call
  python -m scan_reader list
  python -m scan_reader show   <tên|key> [--path]
  python -m scan_reader status
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    # Windows console defaults to cp1252 — Vietnamese output dies without this.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        prog="scan_reader",
        description="ScanReader — bản scan giấy (PDF điền tay) → Markdown nguyên văn")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="chép một PDF scan (hoặc mọi PDF trong thư mục) thành Markdown")
    s.add_argument("target", help="đường dẫn file .pdf hoặc thư mục chứa PDF")
    s.add_argument("--model", default=None,
                   help="vd: gemini-3.6-flash (mặc định) hoặc ollama:qwen3.6 (local, miễn phí)")
    s.add_argument("--pages", default=None,
                   help="chỉ chép các trang này, vd: 1-6 hoặc 1-6,9 (mặc định: toàn bộ)")
    s.add_argument("--pages-per-call", type=int, default=None,
                   help="số trang gửi trong một call Gemini (mặc định 6; local luôn = 1)")
    s.add_argument("--limit", type=int, default=None,
                   help="tối đa N call trong lần chạy này — để dành quota cho việc khác")
    s.add_argument("--force", action="store_true", help="chép lại cả trang đã có")
    s.add_argument("--abort-after", type=int, default=2,
                   help="dừng sau N lỗi liên tiếp (mặc định 2; 0 = không dừng)")
    s.add_argument("--no-beside", action="store_true",
                   help="không ghi bản .md cạnh file PDF gốc (chỉ giữ trong vault)")

    pg = sub.add_parser("pages", help="soi cấu trúc PDF (số trang, ảnh nhúng, hướng xoay) — không tốn call")
    pg.add_argument("pdf")

    sub.add_parser("list", help="các tài liệu đã chép")

    sh = sub.add_parser("show", help="in nội dung Markdown đã chép của một tài liệu")
    sh.add_argument("name", help="tên file (một phần cũng được) hoặc key")
    sh.add_argument("--path", action="store_true", help="chỉ in đường dẫn file .md")

    sub.add_parser("status", help="quota hôm nay + tình trạng store")

    args = ap.parse_args()

    if args.cmd == "scan":
        from second_brain.llm import DEFAULT_MODEL
        from .extract import PAGES_PER_CALL, scan_target
        scan_target(Path(args.target),
                    model=args.model or DEFAULT_MODEL,
                    pages_spec=args.pages,
                    per_call=args.pages_per_call or PAGES_PER_CALL,
                    force=args.force,
                    max_calls=args.limit,
                    abort_after=args.abort_after or None,
                    beside=not args.no_beside)

    elif args.cmd == "pages":
        from .pdf import describe_pdf
        from .extract import PAGES_PER_CALL
        from .pdf import page_count
        print(describe_pdf(Path(args.pdf)))
        n = page_count(Path(args.pdf))
        est = -(-n // PAGES_PER_CALL)        # ceil
        print(f"  · ước tính: {est} call Gemini với {PAGES_PER_CALL} trang/call")

    elif args.cmd == "list":
        from .store import ScanStore
        store = ScanStore()
        recs = store.docs()
        if not recs:
            print("Chưa chép tài liệu nào. Chạy: python -m scan_reader scan <file.pdf>")
        for r in recs:
            n = r.get("pages", 0)
            done = sum(1 for p in range(1, n + 1) if str(p) in r["page_md"])
            flag = "✅" if done == n else f"{done}/{n} trang"
            fail = f" · {len(r['failed'])} chunk lỗi" if r.get("failed") else ""
            print(f"• {Path(r['file']).name} — {flag}{fail}")
            print(f"    → {r.get('output', '(chưa có output)')}")
        print(f"\n{store.summary()}")

    elif args.cmd == "show":
        from .store import ScanStore
        rec = ScanStore().find(args.name)
        if not rec:
            print(f"Không tìm thấy tài liệu khớp “{args.name}”. Xem: python -m scan_reader list")
            return
        out = rec.get("output")
        if args.path or not out or not Path(out).exists():
            print(out or "(chưa có output)")
            return
        print(Path(out).read_text(encoding="utf-8"))

    elif args.cmd == "status":
        from second_brain import quota
        from second_brain.llm import DEFAULT_MODEL
        from .store import ScanStore
        print(quota.status(DEFAULT_MODEL))
        print(quota.status("gemini-3.5-flash-lite"))
        print(ScanStore().summary())


if __name__ == "__main__":
    main()
