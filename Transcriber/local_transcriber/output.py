"""
Output writers — the A+B metadata header, TXT transcript, and CSV.

Format matches v10 so existing downstream consumers (and the Second Brain
ingest) keep working. Written atomically: v10 wrote .txt then .csv, and an
interrupt between the two left a file that `is_done()` counted as unprocessed
forever while the expensive transcription was already paid for.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from .metadata import NOT_EMBEDDED, fmt_duration


def fmt_time(seconds) -> str:
    h, rem = divmod(int(seconds or 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════

def build_header(meta: dict, result: dict, segments: list[dict], cfg) -> str:
    speakers = sorted({s.get("speaker", "SPEAKER_UNKNOWN") for s in segments})
    known    = [s for s in speakers if s != "SPEAKER_UNKNOWN"]

    gps  = meta.get("gps_display", NOT_EMBEDDED)
    maps = meta.get("gps_maps_url")

    lines = [
        "=" * 78,
        "  MEETING TRANSCRIPT",
        "=" * 78,
        "",
        "── A. RECORDING ────────────────────────────────────────────────────────",
        f"  File          : {meta.get('file')}",
        f"  Duration      : {meta.get('duration_fmt', fmt_duration(result.get('duration')))}",
        f"  Original date : {meta.get('original_datetime', 'N/A')}",
        f"  Date source   : {meta.get('datetime_source', 'N/A')}",
        f"  GPS           : {gps}",
    ]
    if maps:
        lines.append(f"  Map           : {maps}")
    lines += [
        f"  Device        : {meta.get('device', 'N/A')}",
        f"  Codec         : {meta.get('codec', 'N/A')}"
        f"  ·  {meta.get('sample_rate', '?')} Hz"
        f"  ·  {meta.get('channels', '?')} ch",
        "",
        "── B. TRANSCRIPTION ────────────────────────────────────────────────────",
        # Deliberately records only what shapes the transcript — model and
        # decode settings. Device, compute type and thread count are properties
        # of the machine, not of the recording; putting them here would mean the
        # same audio yields a different .txt on Colab than on the laptop.
        # Machine provenance belongs in a sidecar, not in the artifact.
        f"  Model         : {cfg.model}  (beam {cfg.beam_size}, "
        f"VAD {'on' if cfg.vad_filter else 'off'})",
        f"  Language      : {result.get('language', 'N/A')}"
        + (f"  (p={result['language_probability']:.2f})"
           if result.get("language_probability") else ""),
        f"  Segments      : {len(segments)}",
        f"  Speakers      : {len(known) if known else 'not diarized'}"
        + (f"  ({', '.join(known)})" if known else ""),
        # UTC with an explicit marker. Colab runs UTC and this laptop runs
        # UTC+7, so a naive local timestamp made the two platforms disagree by
        # seven hours with nothing in the file to explain the gap.
        f"  Transcribed   : {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
    ]
    if meta.get("layer_errors"):
        for tool, err in meta["layer_errors"].items():
            lines.append(f"  Note          : {tool} — {err}")
    lines += ["", "=" * 78, ""]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# WRITERS
# ═══════════════════════════════════════════════════════════════════════════════

def _write_atomic(path: Path, text: str) -> None:
    """
    newline="\\n" is load-bearing, not style.

    Path.write_text defaults to newline=None, which translates every "\\n" to
    "\\r\\n" on Windows and leaves it alone on Linux. The same recording
    transcribed on this laptop and on Colab would then differ in every single
    line ending — so the two platforms could never produce identical files.
    Pinning LF makes the output depend on the audio, not on the OS.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def write_txt(path: Path, header: str, segments: list[dict], show_speakers: bool) -> None:
    body = []
    last = None
    for seg in segments:
        spk = seg.get("speaker", "SPEAKER_UNKNOWN")
        if show_speakers and spk != last:
            body.append(f"\n[{spk}]")
            last = spk
        body.append(f"  ({fmt_time(seg['start'])})  {seg['text']}")
    _write_atomic(path, header + "\n".join(body) + "\n")


def write_csv(path: Path, segments: list[dict], meta: dict) -> None:
    gps = meta.get("gps")
    gps_str = f"{gps[0]:.6f},{gps[1]:.6f}" if gps else ""

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Index", "Start", "End", "Start_fmt", "Speaker", "Text",
                    "Original_DT", "GPS_Coords", "Source_File"])
        for i, seg in enumerate(segments, 1):
            w.writerow([
                i,
                f"{seg['start']:.2f}",
                f"{seg['end']:.2f}",
                fmt_time(seg["start"]),
                seg.get("speaker", ""),
                seg["text"],
                meta.get("original_datetime", ""),
                gps_str,
                meta.get("file", ""),
            ])
    os.replace(tmp, path)


def write_outputs(audio_path: Path, meta: dict, result: dict,
                  segments: list[dict], cfg, diarized: bool) -> tuple[Path, Path]:
    """
    Write .txt and .csv beside the audio.

    utf-8-sig on the CSV so Excel opens Vietnamese correctly — without the BOM
    it mangles diacritics, which matters when every transcript here is Vietnamese.
    """
    out_txt = audio_path.with_suffix(".txt")
    out_csv = audio_path.with_suffix(".csv")

    header = build_header(meta, result, segments, cfg)
    write_txt(out_txt, header, segments, show_speakers=diarized)
    write_csv(out_csv, segments, meta)
    return out_txt, out_csv
