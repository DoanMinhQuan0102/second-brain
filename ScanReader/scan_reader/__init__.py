"""
ScanReader — bản scan giấy (PDF điền tay) → Markdown nguyên văn.

Born 2026-07-28 for "KOI Recall Data.pdf": 60 pages of phone-recall interview
sheets filled in by hand — cursive Vietnamese, ticked boxes, circled scales —
with no text layer at all. The Gemini vision path PhotoRecall proved on
whiteboards reads this handwriting; this branch turns that into a chunked,
fail-forward pipeline whose output can be diffed against the scan page by
page. Nothing is summarised: the deliverable is the paper itself, as text.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]   # Second Brain Project/
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
