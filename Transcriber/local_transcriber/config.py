"""
Configuration for the local (CPU) transcriber.

v10 kept config in a Colab cell with the HF token pasted inline. That token is
still live in seven notebooks on Drive — this reads from the environment or a
gitignored .env instead, and never stores a secret in the file you edit.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# SECRETS
# ═══════════════════════════════════════════════════════════════════════════════

def get_secret(name: str, required: bool = False) -> str | None:
    """Environment first, then a .env file at the project root."""
    val = os.environ.get(name)
    if val:
        return val

    # Walk upward so the shared repo-root .env is found no matter how deep
    # this package is nested (it moved to Transcriber/ in the 2026-07 reorg).
    env_path = next((p / ".env" for p in Path(__file__).resolve().parents
                     if (p / ".env").exists()),
                    Path(__file__).resolve().parents[2] / ".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip().strip('"').strip("'")

    if required:
        raise RuntimeError(f"{name} not set. Add it to {env_path} or the environment.")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Settings:
    """
    Everything the pipeline needs. Defaults are tuned for a 16-core CPU with no
    CUDA device — which is what an Intel Core Ultra / Arc laptop is.
    """

    folder: Path = Path("G:/My Drive/Meet Recordings")

    # ── Model ─────────────────────────────────────────────────────────────────
    # Measured on this machine (Core Ultra 7 255H, 16 threads, int8, beam 5,
    # VAD on) against a 60s Vietnamese clip:
    #
    #     tiny             ~14x realtime    ~2 min per 30-min recording
    #     small            ~4.5x realtime   ~6 min per 30-min recording
    #     large-v3-turbo   ~2.7x realtime   ~11 min per 30-min recording
    #
    # turbo is the default because ~11 minutes for a half-hour interview is
    # perfectly workable, and quality on Vietnamese is far better than small.
    # Drop to 'small' when you want a fast first pass.
    model: str = "large-v3-turbo"
    language: str | None = "vi"          # None = autodetect

    # ── Device ────────────────────────────────────────────────────────────────
    # All three are Optional and resolved in __post_init__, never by
    # default_factory. That keeps an explicit escape hatch: passing
    # Settings(device='cpu', compute_type='int8', cpu_threads=16) reproduces the
    # verified local run argument-for-argument if detection ever misfires.
    #
    # compute_type is DERIVED from device rather than detected separately —
    # float16-on-CPU and int8-on-CUDA are then unrepresentable, not merely
    # discouraged.
    device: str | None = None            # None = autodetect: cuda if present
    compute_type: str | None = None      # None = float16 on cuda, int8 on cpu
    cpu_threads: int | None = None       # None = os.cpu_count(); ignored on cuda

    # ── Diarization (speaker separation) ──────────────────────────────────────
    # Needs an HF token AND accepting the licence for both:
    #   huggingface.co/pyannote/speaker-diarization-3.1
    #   huggingface.co/pyannote/segmentation-3.0
    # Without a token the transcript is still produced, just without speakers.
    diarize: bool = True
    min_speakers: int | None = None
    max_speakers: int | None = None

    # ── Behaviour ─────────────────────────────────────────────────────────────
    skip_done: bool = True               # a file with .txt AND .csv is done
    word_timestamps: bool = True

    # ── Decode settings ───────────────────────────────────────────────────────
    # These shape the transcript text itself, so they live on Settings (a job
    # property) rather than being buried in transcribe(). Pinning them is what
    # lets a Colab run and a laptop run be compared meaningfully.
    beam_size: int = 5
    vad_filter: bool = True              # skip silence — a large CPU saving
    vad_min_silence_ms: int = 500

    cache_dir: Path = Path.home() / ".cache" / "local_transcriber"

    def hf_token(self) -> str | None:
        return get_secret("HF_TOKEN")

    def __post_init__(self):
        self.folder = Path(self.folder)
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if self.device is None:
            self.device = detect_device()
        if self.compute_type is None:
            self.compute_type = "float16" if self.device == "cuda" else "int8"
        if self.cpu_threads is None:
            self.cpu_threads = os.cpu_count() or 8


def detect_device() -> str:
    """
    'cuda' when a usable NVIDIA GPU is present, else 'cpu'.

    torch is optional — it is only needed for diarization — so a missing torch
    means CPU rather than an error. Note this deliberately does not detect the
    Intel Arc iGPU: CTranslate2 has no SYCL/XPU backend, so Arc is not a device
    faster-whisper can target. Reaching it would need an OpenVINO backend.
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:                                          # noqa: BLE001
        pass
    return "cpu"


AUDIO_EXTS = {
    ".mp4", ".mp3", ".m4a", ".wav", ".ogg",
    ".webm", ".flac", ".aac", ".opus", ".wma", ".amr",
}
