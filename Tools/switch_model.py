"""Đổi model đằng sau Claude Code: Claude / GLM / DeepSeek / OpenRouter.

Claude Code đọc ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN lúc khởi động. Trỏ
hai biến đó sang endpoint Anthropic-compatible của nhà khác là chạy được model
khác trong đúng giao diện Claude Code, không sửa dòng code nào.

Vì sao là Python chứ không phải .ps1: Google Drive đóng dấu Mark of the Web
(Zone.Identifier ZoneId=3) lên mọi file trong G:, mà execution policy của máy
là RemoteSigned → script "từ Internet" đòi chữ ký số và bị chặn. Unblock-File
gỡ được một lần nhưng sync lại đóng dấu lại. Python không đụng execution
policy, nên không bao giờ sập vì lý do đó — cùng họ với bài học "REST thắng
SDK khi môi trường cứng đầu" (PLAYBOOK #7).

Cách dùng:
    python switch_model.py                  # xem đang dùng gì
    python switch_model.py openrouter --test
    python switch_model.py --list-free      # model ":free" đang sống
    python switch_model.py deepseek
    python switch_model.py claude           # xoá override
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    import winreg

# Console Windows là cp1252 — tự bẻ sang UTF-8 như các CLI khác trong repo.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# Toàn bộ bề mặt điều khiển. ANTHROPIC_DEFAULT_*_MODEL bắt buộc phải set:
# không có thì Claude Code gửi tên model của Anthropic sang nhà khác và ăn 404.
VARS = [
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]

PROVIDERS = {
    "glm": {
        "label": "Z.ai GLM Coding Plan",
        "base_url": "https://api.z.ai/api/anthropic",
        "key_name": "GLM_API_KEY",
        "sign_up": "https://z.ai/subscribe",
        "big": "glm-5.2",
        "small": "glm-5-turbo",
    },
    "deepseek": {
        "label": "DeepSeek API (trả theo token, không thuê bao)",
        "base_url": "https://api.deepseek.com/anthropic",
        "key_name": "DEEPSEEK_API_KEY",
        "sign_up": "https://platform.deepseek.com/api_keys",
        "big": "deepseek-chat",
        "small": "deepseek-chat",
    },
    # Đường test $0: key không cần thẻ, free tier ~50 request/ngày.
    # Model đuôi ":free" đổi liên tục — dùng --list-free để lấy danh sách sống.
    "openrouter": {
        "label": "OpenRouter (free tier)",
        "base_url": "https://openrouter.ai/api",
        "key_name": "OPENROUTER_API_KEY",
        "sign_up": "https://openrouter.ai/settings/keys",
        "big": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "small": "openai/gpt-oss-20b:free",
    },
}


def read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def set_user_var(name: str, value: str | None) -> None:
    """Ghi vào HKCU\\Environment rồi báo cho hệ thống — tương đương setx
    nhưng không giới hạn 1024 ký tự và xoá được biến."""
    if sys.platform != "win32":
        raise SystemExit("Script này chỉ chạy trên Windows.")
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
    try:
        if value is None:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)
    # WM_SETTINGCHANGE để tiến trình mới thấy ngay, khỏi cần logout.
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 1000, None
    )


def get_user_var(name: str) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
    except OSError:
        return None
    try:
        return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None
    finally:
        winreg.CloseKey(key)


def mask(value: str | None) -> str:
    if not value:
        return "(trống)"
    if len(value) <= 10:
        return "***"
    return value[:6] + "..." + value[-4:]


def http_json(url: str, payload=None, headers=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def show_status() -> None:
    base = get_user_var("ANTHROPIC_BASE_URL")
    print("\n  Claude Code đang trỏ tới:")
    if not base or "api.anthropic.com" in base:
        # Harness của Claude Code tự set api.anthropic.com ở process scope,
        # nên "trống" và "api.anthropic.com" đều nghĩa là Claude gốc.
        print("  → Anthropic (gói Claude bạn đang đăng nhập)")
    else:
        who = next(
            (p["label"] for p in PROVIDERS.values() if p["base_url"] == base),
            "(không rõ)",
        )
        print(f"  → {who}")
        print(f"     base  : {base}")
        print(f"     token : {mask(get_user_var('ANTHROPIC_AUTH_TOKEN'))}")
        model = get_user_var("ANTHROPIC_MODEL")
        if model:
            print(f"     model : {model}")

    print("\n  Tầng local (không qua script này):")
    try:
        tags = http_json("http://127.0.0.1:11434/api/tags", timeout=3)
        for m in tags.get("models", []):
            print(f"     {m['name']:<34} {m['size'] / 1e9:6.1f} GB")
    except Exception:
        print("     Ollama không chạy (127.0.0.1:11434)")
    print()


def list_free() -> None:
    print("\n  Model free đang sống trên OpenRouter:")
    try:
        data = http_json("https://openrouter.ai/api/v1/models", timeout=60)["data"]
        free = sorted((m for m in data if ":free" in m["id"]), key=lambda m: m["id"])
        for m in free:
            print(f"     {m['id']:<52} ctx {m['context_length']:>9,}")
        print(f"\n  ({len(free)} model — đặt vào ANTHROPIC_MODEL để dùng)")
    except Exception as exc:
        print(f"  Không lấy được danh sách: {exc}")
    print()


def test_endpoint(base_url: str, token: str, model: str) -> bool:
    print(f"  Gọi thử {model} ...")
    try:
        r = http_json(
            f"{base_url}/v1/messages",
            payload={
                "model": model,
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "Trả lời đúng hai chữ: xin chào"}],
            },
            headers={
                "x-api-key": token,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        text = next((c.get("text", "") for c in r.get("content", []) if c.get("type") == "text"), "")
        print(f"  OK — model trả lời: {text}")
        return True
    except urllib.error.HTTPError as exc:
        print(f"  LỖI HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")
    except Exception as exc:
        print(f"  LỖI: {exc}")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Đổi model đằng sau Claude Code.")
    ap.add_argument(
        "target",
        nargs="?",
        default="status",
        choices=["status", "claude", *PROVIDERS.keys()],
    )
    ap.add_argument("--test", action="store_true", help="gọi thử endpoint sau khi đổi")
    ap.add_argument("--list-free", action="store_true", help="liệt kê model free của OpenRouter")
    args = ap.parse_args()

    if args.list_free:
        list_free()
        return 0

    if args.target == "status":
        show_status()
        return 0

    if args.target == "claude":
        for v in VARS:
            set_user_var(v, None)
        print("\n  ✓ Đã xoá override — Claude Code quay về gói Claude của bạn.")
        print("    Mở terminal MỚI để có hiệu lực.\n")
        return 0

    p = PROVIDERS[args.target]
    key = read_dotenv(ENV_FILE).get(p["key_name"], "")
    if not key:
        print(f"\n  Chưa có {p['key_name']} trong {ENV_FILE}\n")
        print(f"  Cách lấy: đăng ký {p['label']} tại {p['sign_up']},")
        print("  tạo API key, rồi thêm vào .env một dòng:\n")
        print(f"      {p['key_name']}=sk-...\n")
        print("  (.env đã nằm trong .gitignore — key không vào git.)\n")
        return 1

    set_user_var("ANTHROPIC_BASE_URL", p["base_url"])
    set_user_var("ANTHROPIC_AUTH_TOKEN", key)
    set_user_var("ANTHROPIC_MODEL", p["big"])
    set_user_var("ANTHROPIC_SMALL_FAST_MODEL", p["small"])
    set_user_var("ANTHROPIC_DEFAULT_OPUS_MODEL", p["big"])
    set_user_var("ANTHROPIC_DEFAULT_SONNET_MODEL", p["big"])
    set_user_var("ANTHROPIC_DEFAULT_HAIKU_MODEL", p["small"])

    print(f"\n  ✓ Claude Code → {p['label']}")
    print(f"    base  : {p['base_url']}")
    print(f"    token : {mask(key)}  (từ .env: {p['key_name']})")
    print(f"    model : {p['big']}  /  nhanh: {p['small']}")

    if args.test:
        print()
        if not test_endpoint(p["base_url"], key, p["big"]):
            print("\n  Chưa gọi được. Kiểm tra key còn hạn / gói còn quota.")

    print("\n  Mở terminal MỚI để Claude Code nạp biến.")
    print("  Về lại Claude:  python switch_model.py claude\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
