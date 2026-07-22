"""
Deep metadata extraction — GPS + original datetime.

Port of v10 Cell 5b. Same four layers, each attempted independently so a missing
tool degrades instead of failing:

  L1  ffprobe   creation_time, ISO6709 location (iOS), `location` tag (Android),
                codec, bitrate, sample_rate, channels, duration
  L2  mutagen   MP4 ©xyz atom, ID3 tags, duration, sample_rate
  L3  exiftool  GPSLatitude/Longitude/Altitude, CreateDate, device Make/Model
  L4  file stat mtime/ctime as last resort

On Windows exiftool usually isn't present, so L3 is skipped with a note. L1
already covers iOS Voice Memos and Android recorders, which is where GPS
actually comes from — cloud sources (Meet/Teams/Zoom) never embed it.
"""

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

NOT_EMBEDDED = "Not embedded in this file"


# ═══════════════════════════════════════════════════════════════════════════════
# GPS PARSERS
# ═══════════════════════════════════════════════════════════════════════════════

def parse_iso6709(loc_str: str) -> tuple[float, float, float | None] | None:
    """
    ISO 6709 as written by Apple and Android.
        '+10.7769+106.7009/'          → lat, lon
        '+10.7769+106.7009+10.000/'   → lat, lon, alt
    """
    if not loc_str:
        return None
    m = re.search(r"([+-]\d+\.?\d*)([+-]\d+\.?\d*)([+-]\d+\.?\d*)?", loc_str)
    if not m:
        return None
    lat = float(m.group(1))
    lon = float(m.group(2))
    alt = float(m.group(3)) if m.group(3) else None
    return lat, lon, alt


def _dms_to_decimal(val, ref: str) -> float | None:
    """exiftool may emit decimal degrees or a DMS string like `10 deg 46' 36.48"`."""
    if isinstance(val, (int, float)):
        d = float(val)
    elif isinstance(val, str):
        parts = re.findall(r"[\d.]+", val)
        if len(parts) >= 3:
            d = float(parts[0]) + float(parts[1]) / 60 + float(parts[2]) / 3600
        elif len(parts) == 1:
            d = float(parts[0])
        else:
            return None
    else:
        return None
    if str(ref).upper().startswith(("S", "W")) and d > 0:
        d = -d
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# LAYERS
# ═══════════════════════════════════════════════════════════════════════════════

def _layer1_ffprobe(path: Path) -> dict:
    if not shutil.which("ffprobe"):
        return {"_error": "ffprobe not on PATH"}
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
        if proc.returncode != 0:
            return {"_error": f"ffprobe exit {proc.returncode}"}
        probe = json.loads(proc.stdout or "{}")
    except Exception as e:                                    # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}

    fmt  = probe.get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    out: dict = {}

    if fmt.get("duration"):
        out["duration"] = float(fmt["duration"])
    if fmt.get("bit_rate"):
        out["bitrate"] = int(fmt["bit_rate"])

    if tags.get("creation_time"):
        out["original_datetime"] = tags["creation_time"]
        out["datetime_source"]   = "ffprobe:creation_time"

    # iOS puts it here; Android uses the bare `location` tag.
    for key in ("com.apple.quicktime.location.iso6709", "location", "location-eng"):
        if tags.get(key):
            gps = parse_iso6709(tags[key])
            if gps:
                out["gps"] = gps
                out["gps_source"] = f"ffprobe:{key}"
                break

    for key in ("com.apple.quicktime.make", "com.apple.quicktime.model"):
        if tags.get(key):
            out.setdefault("device", "")
            out["device"] = (out["device"] + " " + tags[key]).strip()

    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "audio":
            out["codec"]       = stream.get("codec_name")
            out["sample_rate"] = int(stream["sample_rate"]) if stream.get("sample_rate") else None
            out["channels"]    = stream.get("channels")
            break

    return out


def _layer2_mutagen(path: Path) -> dict:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return {"_error": "mutagen not installed"}
    try:
        mf = MutagenFile(str(path))
    except Exception as e:                                    # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}
    if mf is None:
        return {"_error": "unrecognised container"}

    out: dict = {}
    info = getattr(mf, "info", None)
    if info is not None:
        if getattr(info, "length", None):
            out["duration"] = float(info.length)
        if getattr(info, "sample_rate", None):
            out["sample_rate"] = int(info.sample_rate)
        if getattr(info, "channels", None):
            out["channels"] = int(info.channels)

    # MP4 ©xyz atom — the same ISO6709 payload ffprobe exposes as a tag.
    try:
        for key in ("\xa9xyz", "©xyz"):
            if key in mf:
                raw = mf[key]
                val = raw[0] if isinstance(raw, list) and raw else raw
                gps = parse_iso6709(str(val))
                if gps:
                    out["gps"] = gps
                    out["gps_source"] = "mutagen:©xyz"
                break
    except Exception:                                          # noqa: BLE001
        pass

    return out


def _layer3_exiftool(path: Path) -> dict:
    if not shutil.which("exiftool"):
        return {"_error": "exiftool not installed (optional)"}
    try:
        proc = subprocess.run(
            ["exiftool", "-json", "-n", "-a", "-G1", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90,
        )
        data = json.loads(proc.stdout or "[]")
        if not data:
            return {}
        et = {k.split(":")[-1]: v for k, v in data[0].items()}
    except Exception as e:                                    # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}

    out: dict = {}
    lat = _dms_to_decimal(et.get("GPSLatitude"), et.get("GPSLatitudeRef", "N"))
    lon = _dms_to_decimal(et.get("GPSLongitude"), et.get("GPSLongitudeRef", "E"))
    if lat is not None and lon is not None:
        alt = et.get("GPSAltitude")
        out["gps"] = (lat, lon, float(alt) if isinstance(alt, (int, float)) else None)
        out["gps_source"] = "exiftool"

    for key in ("CreateDate", "TrackCreateDate", "MediaCreateDate", "DateTimeOriginal"):
        if et.get(key):
            out["original_datetime"] = str(et[key])
            out["datetime_source"]   = f"exiftool:{key}"
            break

    make, model = et.get("Make"), et.get("Model")
    if make or model:
        out["device"] = " ".join(str(x) for x in (make, model) if x)

    return out


def _layer4_stat(path: Path) -> dict:
    st = path.stat()
    ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    return {
        "original_datetime": ts.isoformat(),
        "datetime_source": "file stat:mtime",
        "file_size": st.st_size,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC
# ═══════════════════════════════════════════════════════════════════════════════

def extract_audio_metadata(path) -> dict:
    """
    Run all four layers and merge, earlier layers winning on conflict.

    Layer 4 only ever fills gaps — a file's mtime is the weakest possible claim
    about when a meeting happened, so it must never overwrite a real tag.
    """
    path = Path(path)
    meta: dict = {"file": path.name, "path": str(path), "layer_errors": {}}

    for name, fn in (("ffprobe",  _layer1_ffprobe),
                     ("mutagen",  _layer2_mutagen),
                     ("exiftool", _layer3_exiftool)):
        result = fn(path)
        err = result.pop("_error", None)
        if err:
            meta["layer_errors"][name] = err
        for k, v in result.items():
            if v is not None and k not in meta:
                meta[k] = v

    for k, v in _layer4_stat(path).items():
        meta.setdefault(k, v)

    meta["duration_fmt"]      = fmt_duration(meta.get("duration"))
    meta["gps_display"]       = _gps_display(meta.get("gps"))
    meta["gps_maps_url"]      = _maps_url(meta.get("gps"))
    meta.setdefault("device", "N/A")
    meta.setdefault("codec", "N/A")
    return meta


def _gps_display(gps) -> str:
    if not gps:
        return NOT_EMBEDDED
    lat, lon, alt = gps
    s = f"{lat:.6f}, {lon:.6f}"
    return f"{s} (alt {alt:.0f} m)" if alt is not None else s


def _maps_url(gps) -> str | None:
    if not gps:
        return None
    lat, lon, _ = gps
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"


def fmt_duration(seconds) -> str:
    if not seconds:
        return "N/A"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
