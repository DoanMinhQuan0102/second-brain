# Second Brain — tools

Four working pieces extracted from a personal knowledge-management system: a folder organiser, a transcription pipeline, a handwritten-scan reader, and a small set of Colab and local-model utilities.

Everything here runs on free tiers and consumer hardware — Google Colab, a Drive-backed model cache, and a local Ollama install. Most of the design decisions below exist because of that constraint rather than in spite of it.

Module documentation is in Vietnamese; this page is in English.

---

## Librarian

Tidies a working directory by rule first, and only asks a model about what the rules cannot classify.

Roughly 90 percent of stray files can be placed from extension and folder name alone. Spending an LLM call on those is waste. `rules.py` handles them with no tokens at all: bytecode and OS cruft marked for deletion, loose media routed to the right vault folder, installers to the archive, dated or bracketed folders to research. Only the genuinely ambiguous remainder goes to a local `qwen3:14b`, which returns a bucket and a one-line reason. Low-confidence answers are flagged for a human, never auto-applied.

Two safety properties I would not give up:

**`scan` never touches the disk.** It writes a plan file and stops. `apply` reprints the whole plan, asks for confirmation, and skips every `action=delete` entry unless explicitly allowed with a second flag.

**File contents never leave the machine.** The model sees filenames and a few child names to guess a topic. Nothing else is sent, and the model is local anyway.

The choice of `qwen3:14b` over the larger vision model is deliberate: this job reads names, not pixels, so the 36B model is slower for no benefit. The Gemini free tier is reserved for work that actually needs it.

---

## Transcriber

WhisperX (`large-v3`) with `pyannote.audio` diarization, emitting `.txt` and `.csv`.

Step 0 is a deep metadata pass with `ffprobe`, `mutagen` and `exiftool`, so the rest of the pipeline knows the real sample rate, duration and channel layout instead of inferring them and getting it wrong on the occasional odd file.

---

## ScanReader

Reads handwritten scans and photographed notes into structured Markdown, for material that never existed in digital form.

---

## Tools

Small utilities that remove recurring friction. A provider router that switches Claude Code between backends and puts an otherwise idle integrated GPU to work, and a batch PDF compressor that runs in Colab and leaves the originals untouched.

---

## Engineering notes

Constraints that shaped more than one module.

**Compiled packages cannot live on the Drive mount.** Pure-Python dependencies are cached in a virtualenv on Google Drive and survive across sessions. Anything shipping `.so` files is reinstalled locally every session, because `dlopen()` is not reliable against a FUSE network filesystem. This split is the single biggest reason setup is fast and stable.

**Idempotency keys off SHA-256, not filenames.** State is tracked by content hash, so a renamed file is not reprocessed and a modified one always is.

**Fatal errors break the circuit; transient ones retry.** Quota and invalid-key responses stop the run immediately rather than burning through a retry loop that cannot succeed.

**No silent CPU fallback.** With no GPU present, audio processing raises `RuntimeError` and stops. CPU transcription at this model size is slow enough that a silent fallback looks like a hang, not a degradation.

**Atomic, incremental writes.** Files are written with `os.replace()` and saved as they complete rather than at the end of a batch, so a Colab session dying at 80 percent costs one file instead of the whole run.

**Secrets stay out of the notebooks.** Tokens come from Colab Secrets via `userdata.get()`, never from a literal in a cell.

---

## Scope

This is an extract. The full system is a private monorepo that also holds personal journal and photo-context modules, plus consumer-research tooling written for a previous employer. Only the four general-purpose modules are published here, with their original commit history intact.

---

## Why this exists

I moved from consumer and sensory research in FMCG into statistics, and started an MSc in Statistical Data Science at University College Dublin in September 2026. The volume of lecture audio, slides and handwritten notes made a manual workflow untenable inside the first fortnight. These are the parts I built instead, and still use.
