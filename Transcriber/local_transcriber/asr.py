"""
Transcription + diarization, CPU only.

Differences from v10, all forced by having no CUDA device:

  · faster-whisper directly instead of whisperx. whisperx is a wrapper around
    this same engine plus a wav2vec2 alignment pass; on CPU that extra pass costs
    more than it returns, and faster-whisper emits word timestamps natively.
  · int8 quantisation instead of float16 (float16 is a GPU compute type).
  · VAD filtering on by default — skipping silence is the single largest CPU
    saving available, often 30-50% on interview audio.
  · v10 raised RuntimeError when no GPU was found. That check is the whole
    reason this file exists, so it is gone.
"""

import gc
import time
from pathlib import Path

from .audio import SAMPLE_RATE, decode_audio, install_av_stub
from .config import Settings


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSCRIPTION
# ═══════════════════════════════════════════════════════════════════════════════

def load_model(cfg: Settings):
    """Load the Whisper model. Cached on disk after the first download."""
    install_av_stub()
    from faster_whisper import WhisperModel

    t0 = time.time()
    kwargs = {
        "device": cfg.device,
        "compute_type": cfg.compute_type,
        "download_root": str(cfg.cache_dir / "faster-whisper"),
    }
    if cfg.device == "cpu":
        kwargs["cpu_threads"] = cfg.cpu_threads      # accepted but ignored on cuda

    model = WhisperModel(cfg.model, **kwargs)

    detail = (f"{cfg.device}/{cfg.compute_type}" if cfg.device == "cuda"
              else f"{cfg.device}/{cfg.compute_type}/{cfg.cpu_threads} threads")
    print(f"   ✅ {cfg.model} [{detail}] ({time.time() - t0:.1f}s)")
    return model


def transcribe(model, audio_path, cfg: Settings) -> dict:
    """
    Decode with ffmpeg, then transcribe.

    Returns {"segments": [...], "language": str, "duration": float}, each segment
    carrying start/end/text and (optionally) word-level timings.
    """
    audio = decode_audio(audio_path, SAMPLE_RATE)

    segments_iter, info = model.transcribe(
        audio,
        language=cfg.language,
        word_timestamps=cfg.word_timestamps,
        vad_filter=cfg.vad_filter,
        vad_parameters=({"min_silence_duration_ms": cfg.vad_min_silence_ms}
                        if cfg.vad_filter else None),
        beam_size=cfg.beam_size,
    )

    segments = []
    for seg in segments_iter:                     # generator — work happens here
        words = None
        if cfg.word_timestamps and seg.words:
            words = [{"start": w.start, "end": w.end, "word": w.word} for w in seg.words]
        segments.append({
            "start": seg.start,
            "end":   seg.end,
            "text":  seg.text.strip(),
            "words": words,
        })

    return {
        "segments": segments,
        "language": info.language,
        "language_probability": getattr(info, "language_probability", None),
        "duration": info.duration,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DIARIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def load_diarizer(cfg: Settings):
    """
    pyannote speaker-diarization-3.1 on CPU.

    Returns None (with an explanation) rather than raising, so a missing token or
    unaccepted licence degrades to a speaker-less transcript instead of losing
    the whole run.
    """
    token = cfg.hf_token()
    if not token:
        print("   ⚠️  No HF_TOKEN — transcript will have no speaker labels.")
        return None

    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError:
        print("   ⚠️  pyannote.audio not installed — no speaker labels.\n"
              "      pip install pyannote.audio torch --index-url https://download.pytorch.org/whl/cpu")
        return None

    t0 = time.time()

    # pyannote renamed this kwarg: 4.x takes `token=`, 3.x took `use_auth_token=`.
    # Passing the wrong one raises TypeError, which a bare `except` would report
    # as "accept the licence" — sending you to fix a licence that was never the
    # problem. Try both, and keep TypeError out of the licence branch.
    pipe = None
    last_err: Exception | None = None
    for kwargs in ({"token": token}, {"use_auth_token": token}):
        try:
            pipe = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", **kwargs)
            break
        except TypeError as e:
            last_err = e
            continue
        except Exception as e:                                 # noqa: BLE001
            print(f"   ⚠️  Diarization unavailable ({type(e).__name__}: {e}).\n"
                  "      Accept the licence at hf.co/pyannote/speaker-diarization-3.1 "
                  "and hf.co/pyannote/segmentation-3.0")
            return None

    if pipe is None:
        print(f"   ⚠️  pyannote API mismatch ({last_err}) — no speaker labels.")
        return None

    # from_pretrained returns None on an auth/licence failure instead of raising.
    pipe.to(torch.device(cfg.device))
    print(f"   ✅ diarization pipeline on {cfg.device} ({time.time() - t0:.1f}s)")
    return pipe


def diarize(pipe, audio_path, cfg: Settings, work_dir: Path | None = None) -> list[dict]:
    """
    Return [{start, end, speaker}] turns.

    Passes the waveform in memory rather than a file path. pyannote would
    otherwise decode via torchcodec, whose DLLs don't load here either:

        Could not find module 'torchcodec\\libtorchcodec_core8.dll'

    Feeding it a {"waveform", "sample_rate"} dict is pyannote's own documented
    escape hatch for exactly this, and it reuses the same ffmpeg decode path
    that gets us past the PyAV block — so audio enters the process one way only.
    """
    import torch

    audio = decode_audio(audio_path, SAMPLE_RATE)
    waveform = torch.from_numpy(audio).unsqueeze(0)     # (channel, time)

    kwargs = {}
    if cfg.min_speakers is not None:
        kwargs["min_speakers"] = cfg.min_speakers
    if cfg.max_speakers is not None:
        kwargs["max_speakers"] = cfg.max_speakers

    try:
        annotation = pipe(
            {"waveform": waveform, "sample_rate": SAMPLE_RATE}, **kwargs
        )
        return [
            {"start": turn.start, "end": turn.end, "speaker": speaker}
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]
    finally:
        gc.collect()


def assign_speakers(segments: list[dict], turns: list[dict]) -> list[dict]:
    """
    Label each segment with the speaker it overlaps most.

    Overlap-by-duration rather than midpoint lookup: a segment straddling a
    handover gets attributed to whoever actually said most of it.
    """
    if not turns:
        for seg in segments:
            seg["speaker"] = "SPEAKER_UNKNOWN"
        return segments

    for seg in segments:
        best, best_overlap = "SPEAKER_UNKNOWN", 0.0
        for turn in turns:
            overlap = min(seg["end"], turn["end"]) - max(seg["start"], turn["start"])
            if overlap > best_overlap:
                best, best_overlap = turn["speaker"], overlap
        seg["speaker"] = best
    return segments
