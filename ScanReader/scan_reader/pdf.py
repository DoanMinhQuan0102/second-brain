"""
Page images for the model — the embedded scan itself, not a re-render.

Scanner apps write one JPEG per page and set /Rotate instead of rotating
pixels. Two consequences this module encodes:
  · `extract_image()` returns the untouched scanner JPEG — PhotoRecall
    measured +30% small-text OCR from feeding originals instead of
    re-encodes, so the stream passes through byte-identical when it can;
  · when /Rotate isn't 0 the raw stream is SIDEWAYS (KOI Recall Data:
    2340×1654 landscape + /Rotate 270) — handwriting OCR dies on rotated
    text, so one PIL transpose at q92 puts it upright first.
Pages that are not a single clean full-page image (text layer, vectors,
rotated/flipped placement matrix, exotic codecs) fall back to a 220-dpi
render, which fitz rotates correctly by itself.
"""

import io
import re
import tempfile
from pathlib import Path

import fitz
from PIL import Image

RENDER_DPI = 220
MAX_SIDE = 3000          # px — larger pages are downscaled (upload sanity; Gemini tiles anyway)
JPEG_QUALITY = 92

# PDF /Rotate is clockwise-on-display; PIL transposes are counter-clockwise.
_ROT_TO_PIL = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}


def page_count(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def prepare_pages(pdf_path: Path, page_nos: list[int]) -> list[Path]:
    """Render/extract the given 1-based pages into upright JPEG temp files."""
    out_dir = Path(tempfile.gettempdir()) / "scan_reader"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w-]+", "_", Path(pdf_path).stem)[:40] or "doc"

    paths: list[Path] = []
    with fitz.open(pdf_path) as doc:
        for n in page_nos:
            got = _embedded_upright(doc, doc[n - 1])
            if got is None:
                pix = doc[n - 1].get_pixmap(dpi=RENDER_DPI)
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=JPEG_QUALITY)
                got = buf.getvalue(), ".jpg"
            data, suffix = got
            dest = out_dir / f"{stem}_p{n:03d}{suffix}"
            dest.write_bytes(data)
            paths.append(dest)
    return paths


def _embedded_upright(doc, page) -> tuple[bytes, str] | None:
    """Original embedded scan, rotated upright — or None → render fallback."""
    imgs = page.get_images(full=True)
    if len(imgs) != 1 or page.get_text().strip():
        return None
    info = page.get_image_info()
    if len(info) != 1:
        return None
    a, b, c, d = info[0]["transform"][:4]
    if abs(b) > 1e-3 or abs(c) > 1e-3 or a <= 0 or d <= 0:
        return None                       # rotation/flip baked into placement
    raw = doc.extract_image(imgs[0][0])
    ext = raw.get("ext", "").lower()
    if ext not in ("jpg", "jpeg", "png"):
        return None                       # CCITT/JBIG2/… — let fitz decode it
    data = raw["image"]
    rot = page.rotation % 360

    with Image.open(io.BytesIO(data)) as im:
        if rot == 0 and max(im.size) <= MAX_SIDE:
            return data, (".png" if ext == "png" else ".jpg")   # byte-identical
        im = im.convert("RGB")
        if rot:
            im = im.transpose(_ROT_TO_PIL[rot])
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=JPEG_QUALITY)
        return buf.getvalue(), ".jpg"


def describe_pdf(pdf_path: Path) -> str:
    """0-call structural report: page sizes, embedded images, rotation."""
    from collections import Counter

    lines = []
    with fitz.open(pdf_path) as doc:
        lines.append(f"{Path(pdf_path).name}: {doc.page_count} trang, "
                     f"{Path(pdf_path).stat().st_size / 1e6:.1f} MB")
        kinds = Counter()
        for i in range(doc.page_count):
            page = doc[i]
            imgs = page.get_images(full=True)
            if len(imgs) == 1 and not page.get_text().strip():
                kinds[f"scan {imgs[0][2]}x{imgs[0][3]} /Rotate {page.rotation}"] += 1
            else:
                kinds[f"hỗn hợp ({len(imgs)} ảnh, "
                      f"{len(page.get_text())} ký tự text)"] += 1
        for kind, n in kinds.most_common():
            lines.append(f"  · {n} trang: {kind}")
    return "\n".join(lines)
