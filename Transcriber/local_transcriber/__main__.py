"""CLI:  python -m local_transcriber <folder> [options]"""

import argparse
from pathlib import Path

from .config import Settings
from .metadata import extract_audio_metadata
from .pipeline import Transcriber, is_done, scan


def main() -> int:
    p = argparse.ArgumentParser(
        prog="local_transcriber",
        description="Transcribe meeting recordings locally on CPU (v10, no GPU).",
    )
    p.add_argument("folder", nargs="?", default=None,
                   help="folder of recordings (searched recursively)")
    p.add_argument("--model", default=None,
                   help="large-v3-turbo (default) | large-v3 | medium | small | tiny")
    p.add_argument("--language", default=None, help="vi, en, ... (omit to autodetect)")
    p.add_argument("--threads", type=int, default=None, help="CPU threads")
    p.add_argument("--no-diarize", action="store_true", help="skip speaker separation")
    p.add_argument("--min-speakers", type=int, default=None)
    p.add_argument("--max-speakers", type=int, default=None)
    p.add_argument("--redo", action="store_true", help="re-transcribe files already done")
    p.add_argument("--scan-only", action="store_true",
                   help="list files with metadata, transcribe nothing")
    args = p.parse_args()

    kwargs: dict = {}
    if args.folder:        kwargs["folder"] = Path(args.folder)
    if args.model:         kwargs["model"] = args.model
    if args.language:      kwargs["language"] = args.language
    if args.threads:       kwargs["cpu_threads"] = args.threads
    if args.no_diarize:    kwargs["diarize"] = False
    if args.min_speakers:  kwargs["min_speakers"] = args.min_speakers
    if args.max_speakers:  kwargs["max_speakers"] = args.max_speakers
    if args.redo:          kwargs["skip_done"] = False

    cfg = Settings(**kwargs)

    if args.scan_only:
        files = scan(cfg.folder)
        print(f"📁 {cfg.folder} — {len(files)} file(s)\n")
        print(f"{'File':<44} {'Dur':>8}  {'Date':<22} {'GPS':<26} Done")
        print("-" * 112)
        for f in files:
            m = extract_audio_metadata(f)
            print(f"{f.name[:42]:<44} {m.get('duration_fmt', 'N/A'):>8}  "
                  f"{str(m.get('original_datetime', 'N/A'))[:20]:<22} "
                  f"{m.get('gps_display', 'N/A')[:24]:<26} "
                  f"{'✓' if is_done(f) else ''}")
        return 0

    Transcriber(cfg).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
