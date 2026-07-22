"""
Orchestration — scan a folder, transcribe what isn't done, report.

Models load once for the whole batch. v1.1 of the Second Brain had a bug where
`'asr_model' not in dir()` reloaded the model for every single file; the same
regression hit meeting_transcriber between v5 and v6. Holding the models in a
Transcriber instance makes that class of bug structurally impossible.
"""

import time
from pathlib import Path

from .asr import (assign_speakers, diarize, load_diarizer, load_model,
                  transcribe)
from .config import AUDIO_EXTS, Settings
from .metadata import extract_audio_metadata
from .output import write_outputs


def scan(folder: Path) -> list[Path]:
    """Every audio file under `folder`, sorted, recursive."""
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )


def is_done(audio: Path) -> bool:
    return audio.with_suffix(".txt").exists() and audio.with_suffix(".csv").exists()


class Transcriber:
    """Holds the loaded models across a batch."""

    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or Settings()
        self._model = None
        self._diarizer = None
        self._diarizer_tried = False

    # ── Lazy model access ─────────────────────────────────────────────────────

    @property
    def model(self):
        if self._model is None:
            print("🤖 Loading Whisper...")
            self._model = load_model(self.cfg)
        return self._model

    @property
    def diarizer(self):
        if not self.cfg.diarize:
            return None
        if not self._diarizer_tried:
            print("🗣️  Loading diarization...")
            self._diarizer = load_diarizer(self.cfg)
            self._diarizer_tried = True
        return self._diarizer

    # ── One file ──────────────────────────────────────────────────────────────

    def process(self, audio: Path, index: int = 1, total: int = 1) -> dict:
        audio = Path(audio)
        rel = audio.name
        size_mb = audio.stat().st_size / 1024 / 1024

        if self.cfg.skip_done and is_done(audio):
            print(f"[{index}/{total}] ⏭  skip (done): {rel}")
            return {"file": str(audio), "status": "skipped"}

        print(f"\n[{index}/{total}] ▶  {rel}  ({size_mb:.1f} MB)")
        t_start = time.time()

        print("   0: metadata (ffprobe → mutagen → exiftool → stat)")
        meta = extract_audio_metadata(audio)
        print(f"      date : {meta.get('original_datetime')} ({meta.get('datetime_source')})")
        print(f"      gps  : {meta.get('gps_display')}")
        print(f"      dur  : {meta.get('duration_fmt')} · {meta.get('codec')}")

        print("   1: transcribing...")
        t0 = time.time()
        result = transcribe(self.model, audio, self.cfg)
        segments = result["segments"]
        t_asr = time.time() - t0
        audio_secs = result.get("duration") or meta.get("duration") or 0
        speed = f"{audio_secs / t_asr:.1f}x realtime" if t_asr > 0 and audio_secs else ""
        print(f"      {len(segments)} segments in {t_asr:.0f}s  {speed}")

        diarized = False
        pipe = self.diarizer
        if pipe is not None:
            print("   2: diarizing...")
            t0 = time.time()
            try:
                turns = diarize(pipe, audio, self.cfg, self.cfg.cache_dir)
                assign_speakers(segments, turns)
                n_spk = len({t["speaker"] for t in turns})
                diarized = True
                print(f"      {n_spk} speakers, {len(turns)} turns in {time.time() - t0:.0f}s")
            except Exception as e:                             # noqa: BLE001
                print(f"      ⚠️  diarization failed ({type(e).__name__}: {e}) — continuing without")
                assign_speakers(segments, [])
        else:
            assign_speakers(segments, [])

        out_txt, out_csv = write_outputs(audio, meta, result, segments, self.cfg, diarized)
        print(f"   ✅ {out_txt.name} + {out_csv.name}  ({time.time() - t_start:.0f}s total)")

        return {
            "file": str(audio),
            "status": "ok",
            "segments": len(segments),
            "diarized": diarized,
            "seconds": time.time() - t_start,
            "txt": str(out_txt),
            "csv": str(out_csv),
        }

    # ── Batch ─────────────────────────────────────────────────────────────────

    def run(self, folder: Path | None = None) -> list[dict]:
        folder = Path(folder or self.cfg.folder)
        files = scan(folder)
        pending = [f for f in files if not (self.cfg.skip_done and is_done(f))]

        print(f"📁 {folder}")
        print(f"   {len(files)} audio file(s) · {len(pending)} pending · "
              f"{len(files) - len(pending)} done\n")
        if not pending:
            print("Nothing to do.")
            return []

        results = []
        for i, audio in enumerate(pending, 1):
            try:
                results.append(self.process(audio, i, len(pending)))
            except Exception as e:                             # noqa: BLE001
                print(f"   ❌ {type(e).__name__}: {e}")
                results.append({"file": str(audio), "status": "failed", "error": str(e)})

        ok = sum(r["status"] == "ok" for r in results)
        failed = [r for r in results if r["status"] == "failed"]
        print(f"\n{'=' * 60}\n✅ {ok}/{len(pending)} transcribed")
        for r in failed:
            print(f"   ❌ {Path(r['file']).name}: {r['error'][:90]}")
        return results
