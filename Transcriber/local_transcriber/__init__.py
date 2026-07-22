"""
local_transcriber — meeting_transcriber_v10, rebuilt to run on a laptop.

No Colab, no Drive mount, no CUDA. Same outputs: a .txt transcript with the
A+B metadata header and a .csv, written next to each audio file.

    from local_transcriber import Settings, Transcriber

    cfg = Settings(folder=r"G:\\My Drive\\Meet Recordings", language="vi")
    Transcriber(cfg).run()

Or from a terminal:

    python -m local_transcriber "G:\\My Drive\\Meet Recordings" --model small
"""

from .config import AUDIO_EXTS, Settings
from .metadata import extract_audio_metadata
from .pipeline import Transcriber, is_done, scan

__version__ = "10.0-local"

__all__ = [
    "Settings", "Transcriber", "scan", "is_done",
    "extract_audio_metadata", "AUDIO_EXTS",
]
