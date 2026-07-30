"""
Plan — kế hoạch dọn dẹp dạng JSON, không bao giờ tự thực thi khi tạo ra.

scan() chỉ ĐỌC đĩa và GHI một file kế hoạch. apply() mới thật sự động vào
file, và chỉ sau khi người dùng xem qua + gõ "yes" (hoặc truyền --yes).
apply() không bao giờ xóa — action "delete" luôn bị bỏ qua trừ khi gọi kèm
--allow-delete, để một lần chạy nhầm không xóa mất gì.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .rules import Verdict, classify_entry, sweep_junk

# Luôn im lặng bỏ qua — hạ tầng repo, không phải "tài nguyên tải về".
_ALWAYS_SKIP = {".git", ".claude", "vault"}


def _git_tracked_top_level(root: Path) -> set[str]:
    """Tên (thành phần đầu tiên của path) mọi file git đang track — coi là mã
    nguồn/tài liệu đã có chỗ, không cần báo cáo lại. Trả về rỗng nếu không
    phải repo git hoặc git không chạy được (không chặn scan vì việc này)."""
    if not (root / ".git").exists():
        return set()
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.split("/", 1)[0] for line in out.splitlines() if line}


@dataclass
class PlanItem:
    src: str          # đường dẫn tuyệt đối
    action: str        # "move" | "delete" | "flag"
    dest: str | None    # đường dẫn đích tuyệt đối, nếu action == "move"
    reason: str
    source: str        # "rule" | "llm"


def _safe_item(child: Path, action: str, dest_abs: str | None, reason: str, source: str) -> PlanItem:
    """Chặn move vô nghĩa: đích trùng nguồn, hoặc đích nằm bên trong chính
    nguồn (VD: đề xuất chuyển '_archive' vào 'repo/_archive' — dest == src)."""
    if action == "move" and dest_abs:
        dest = Path(dest_abs)
        final = dest / child.name if dest.is_dir() else dest
        try:
            final.resolve().relative_to(child.resolve())
            is_inside_self = True
        except ValueError:
            is_inside_self = final.resolve() == child.resolve()
        if is_inside_self:
            return PlanItem(str(child), "flag", None,
                             f"{reason} — nhưng đích trùng/nằm trong chính nó, bỏ qua tự động, tự xem",
                             source)
    return PlanItem(str(child), action, dest_abs, reason, source)


def build_plan(target: Path, use_llm: bool = True, sweep: bool = True) -> list[PlanItem]:
    items: list[PlanItem] = []
    repo_root = target  # librarian scan luôn nhận target = gốc muốn dọn
    known = _ALWAYS_SKIP | _git_tracked_top_level(target)

    if sweep:
        for junk in sweep_junk(target):
            items.append(PlanItem(str(junk), "delete", None,
                                   "rác biết mặt (bytecode/cache/temp)", "rule"))
        junk_paths = {i.src for i in items}
    else:
        junk_paths = set()

    ambiguous: list[Path] = []
    for child in sorted(target.iterdir()):
        if child.name in known:
            continue
        if str(child) in junk_paths:
            continue
        v = classify_entry(child)
        if v.action == "ambiguous":
            ambiguous.append(child)
            continue
        dest_abs = str(repo_root / v.dest) if v.dest else None
        items.append(_safe_item(child, v.action, dest_abs, v.reason, v.source))

    if use_llm and ambiguous:
        from .ollama_classify import classify_ambiguous
        for child in ambiguous:
            v = classify_ambiguous(child)
            dest_abs = str(repo_root / v.dest) if v.dest else None
            items.append(_safe_item(child, v.action, dest_abs, v.reason, v.source))
    else:
        for child in ambiguous:
            items.append(PlanItem(str(child), "flag", None,
                                   "không khớp luật nào, LLM tắt (--no-llm) — tự xem", "rule"))

    return items


def save_plan(items: list[PlanItem], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "items": [asdict(i) for i in items],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_plan(path: Path) -> list[PlanItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [PlanItem(**i) for i in data["items"]]


def print_plan(items: list[PlanItem]) -> None:
    by_action: dict[str, list[PlanItem]] = {}
    for i in items:
        by_action.setdefault(i.action, []).append(i)

    labels = {"move": "DI CHUYỂN", "delete": "XÓA (rác)", "flag": "CẦN TỰ XEM"}
    for action in ("move", "delete", "flag"):
        group = by_action.get(action, [])
        if not group:
            continue
        print(f"\n── {labels[action]} ({len(group)}) " + "─" * 40)
        for i in group:
            name = Path(i.src).name
            tag = "🤖" if i.source == "llm" else "•"
            if i.action == "move":
                print(f"  {tag} {name}\n      → {i.dest}\n      {i.reason}")
            else:
                print(f"  {tag} {name}\n      {i.reason}")


def apply_plan(items: list[PlanItem], allow_delete: bool = False) -> None:
    moved = skipped_delete = failed = 0
    for i in items:
        src = Path(i.src)
        if not src.exists():
            print(f"  ⚠ bỏ qua (không còn tồn tại): {src}")
            continue

        if i.action == "flag":
            continue

        if i.action == "delete":
            if not allow_delete:
                skipped_delete += 1
                continue
            try:
                if src.is_dir():
                    shutil.rmtree(src)
                else:
                    src.unlink()
                print(f"  🗑 đã xóa: {src}")
            except OSError as e:
                print(f"  ✗ lỗi khi xóa {src}: {e}")
                failed += 1
            continue

        if i.action == "move":
            dest = Path(i.dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            final_dest = dest / src.name if dest.is_dir() else dest
            if final_dest.exists():
                print(f"  ⚠ bỏ qua (đích đã có): {src} → {final_dest}")
                continue
            try:
                shutil.move(str(src), str(final_dest))
                print(f"  ✅ đã chuyển: {src.name} → {final_dest}")
                moved += 1
            except OSError as e:
                print(f"  ✗ lỗi khi chuyển {src}: {e}")
                failed += 1

    msg = f"\nXong: {moved} đã chuyển"
    if allow_delete:
        deleted = sum(1 for i in items if i.action == "delete" and not Path(i.src).exists())
        msg += f", {deleted} đã xóa"
    elif skipped_delete:
        msg += f", {skipped_delete} mục xóa bị bỏ qua (thêm --allow-delete nếu muốn xóa thật)"
    print(msg + f", {failed} lỗi.")
