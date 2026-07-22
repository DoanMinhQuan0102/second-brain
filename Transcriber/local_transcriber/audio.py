"""
Audio decoding via ffmpeg instead of PyAV.

Why this exists: Smart App Control is enforced on this machine (CI policy state
1), and it blocks PyAV's bundled DLLs — `import av` dies with "An Application
Control policy has blocked this file". faster-whisper imports av at module load,
so the whole library is unusable without a workaround.

ctranslate2 and onnxruntime load fine, so only the decoder needs replacing.
ffmpeg is installed and signed, so we decode through it and register a stub `av`
module before faster_whisper is imported. `decode_audio` is the only thing that
touches av, and we never call it.

Side benefit: fewer wheels to install, and ffmpeg tolerates more containers.
"""

import shutil
import subprocess
import sys
import types
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


# ═══════════════════════════════════════════════════════════════════════════════
# PYAV STUB  (must run before `import faster_whisper`)
# ═══════════════════════════════════════════════════════════════════════════════

def install_av_stub() -> bool:
    """
    Register a placeholder `av` module so faster_whisper imports cleanly.

    Returns True if a stub was installed, False if the real PyAV works and was
    left alone. Idempotent.
    """
    if "av" in sys.modules:
        return not hasattr(sys.modules["av"], "__version__")

    try:
        import av  # noqa: F401  — real PyAV works here; nothing to do
        return False
    except Exception:                                          # noqa: BLE001
        pass

    av_mod = types.ModuleType("av")

    class _InvalidDataError(Exception):
        pass

    error_mod = types.ModuleType("av.error")
    error_mod.InvalidDataError = _InvalidDataError

    def _blocked(*_args, **_kwargs):
        raise RuntimeError(
            "PyAV is blocked by Smart App Control on this machine. "
            "Decode with local_transcriber.audio.decode_audio() instead of "
            "passing a file path to faster-whisper."
        )

    audio_mod     = types.ModuleType("av.audio")
    resampler_mod = types.ModuleType("av.audio.resampler")
    fifo_mod      = types.ModuleType("av.audio.fifo")
    resampler_mod.AudioResampler = _blocked
    fifo_mod.AudioFifo           = _blocked
    audio_mod.resampler = resampler_mod
    audio_mod.fifo      = fifo_mod

    av_mod.error = error_mod
    av_mod.audio = audio_mod
    av_mod.open  = _blocked

    for name, mod in (("av", av_mod), ("av.error", error_mod),
                      ("av.audio", audio_mod),
                      ("av.audio.resampler", resampler_mod),
                      ("av.audio.fifo", fifo_mod)):
        sys.modules[name] = mod

    return True


# ═══════════════════════════════════════════════════════════════════════════════
# DECODING
# ═══════════════════════════════════════════════════════════════════════════════

def decode_audio(path, sampling_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    Any container → mono float32 numpy array at `sampling_rate`.

    This is what gets handed to faster-whisper. Piping s16le straight out of
    ffmpeg avoids writing a temp WAV for the transcription path entirely.
    """
    _require_ffmpeg()
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-threads", "0", "-i", str(path),
         "-vn", "-f", "s16le", "-acodec", "pcm_s16le",
         "-ar", str(sampling_rate), "-ac", "1", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg failed decoding {Path(path).name}:\n{tail}")

    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def to_wav(path, out_wav, sampling_rate: int = SAMPLE_RATE) -> Path:
    """
    Write a 16 kHz mono WAV. Diarization needs a real file on disk, unlike
    transcription which takes the array directly.
    """
    _require_ffmpeg()
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", str(path), "-vn",
         "-acodec", "pcm_s16le", "-ar", str(sampling_rate), "-ac", "1",
         "-y", str(out_wav)],
        capture_output=True,
    )
    if proc.returncode != 0 or not out_wav.exists():
        tail = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg failed writing WAV:\n{tail}")
    return out_wav


def _require_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it with:  winget install Gyan.FFmpeg"
        )
