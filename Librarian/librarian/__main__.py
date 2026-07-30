"""
CLI:
  python -m librarian scan [PATH]           # đọc, đề xuất, ghi plan — không đụng file
  python -m librarian scan [PATH] --no-llm  # chỉ dùng luật cứng, bỏ qua qwen3:14b
  python -m librarian apply [PLAN]          # thực thi MOVE trong plan (hỏi trước)
  python -m librarian apply [PLAN] --yes --allow-delete   # cho batch/không hỏi

Mặc định PATH = gốc repo (thư mục chứa CLAUDE.md), PLAN = vault/processed/librarian_plan.json
"""

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PLAN = _REPO_ROOT / "vault" / "processed" / "librarian_plan.json"


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="librarian",
                                  description="Dọn thư mục bằng luật cứng + qwen3:14b local")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="quét, đề xuất, ghi plan — không đụng file nào")
    s.add_argument("path", nargs="?", default=str(_REPO_ROOT),
                   help="thư mục cần dọn (mặc định: gốc repo)")
    s.add_argument("--no-llm", action="store_true", help="chỉ dùng luật cứng, bỏ qua model")
    s.add_argument("--no-junk-sweep", action="store_true", help="bỏ qua quét rác đệ quy")
    s.add_argument("--plan-out", default=str(_DEFAULT_PLAN))

    a = sub.add_parser("apply", help="thực thi một plan đã xem qua")
    a.add_argument("plan", nargs="?", default=str(_DEFAULT_PLAN))
    a.add_argument("--yes", action="store_true", help="không hỏi xác nhận (cho script)")
    a.add_argument("--allow-delete", action="store_true",
                   help="cho phép thực thi các mục action=delete (mặc định luôn bỏ qua)")

    args = ap.parse_args()

    from .plan import apply_plan, build_plan, load_plan, print_plan, save_plan

    if args.cmd == "scan":
        target = Path(args.path).resolve()
        if not target.is_dir():
            print(f"Không phải thư mục: {target}")
            sys.exit(1)
        print(f"🔍 Đang quét {target} ...")
        items = build_plan(target, use_llm=not args.no_llm, sweep=not args.no_junk_sweep)
        if not items:
            print("Không có gì để đề xuất — thư mục đã gọn.")
            return
        print_plan(items)
        out = Path(args.plan_out)
        save_plan(items, out)
        n_move = sum(1 for i in items if i.action == "move")
        n_del = sum(1 for i in items if i.action == "delete")
        n_flag = sum(1 for i in items if i.action == "flag")
        print(f"\n📄 Đã ghi plan: {out}  ({n_move} di chuyển, {n_del} xóa, {n_flag} cần tự xem)")
        print(f"   Xem lại rồi chạy: python -m librarian apply {out}")
        return

    if args.cmd == "apply":
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"Không tìm thấy plan: {plan_path}\nChạy `python -m librarian scan` trước.")
            sys.exit(1)
        items = load_plan(plan_path)
        print_plan(items)
        if not args.yes:
            reply = input("\nThực thi các mục MOVE ở trên? (gõ 'yes' để tiếp tục) ")
            if reply.strip().lower() != "yes":
                print("Đã hủy — không có gì bị thay đổi.")
                return
        apply_plan(items, allow_delete=args.allow_delete)


if __name__ == "__main__":
    main()
