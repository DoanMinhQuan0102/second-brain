# Meeting Transcriber — local (CPU) edition

`meeting_transcriber_v10.ipynb` rebuilt to run in VS Code on this laptop. Same
outputs, no Colab, no Drive mount, no CUDA.

Nhánh con của **Second Brain Project** — mọi lệnh chạy từ thư mục này:

```powershell
cd "G:\My Drive\Second Brain Project\Transcriber"
```

## Setup

```powershell
pip install -r requirements-local.txt
```

ffmpeg is required and already installed. If it goes missing:
`winget install Gyan.FFmpeg`

Speaker separation is optional and adds ~2.5 GB:

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install pyannote.audio
```

Then add the token to the shared `.env` at the repo root
(`G:\My Drive\Second Brain Project\.env`, already gitignored):

```
HF_TOKEN=hf_your_token_here
```

and accept both licences, or the pipeline silently falls back to a transcript
with no speaker labels:

- <https://huggingface.co/pyannote/speaker-diarization-3.1>
- <https://huggingface.co/pyannote/segmentation-3.0>

## Use

Open `meeting_transcriber_local.ipynb` in VS Code, edit Cell 2, run Cells 2→4.

Or from a terminal:

```powershell
python -m local_transcriber "G:\My Drive\Meet Recordings" --scan-only
python -m local_transcriber "G:\My Drive\Meet Recordings" --model small --no-diarize
python -m local_transcriber "G:\My Drive\Meet Recordings" --min-speakers 2 --max-speakers 2
```

Outputs `.txt` and `.csv` beside each recording, exactly like v10.

## Speed

Measured on this machine (Core Ultra 7 255H, 16 threads, int8, beam 5, VAD on),
60-second Vietnamese clip:

| model | speed | 30-min recording |
|---|---|---|
| `tiny` | ~14× realtime | ~2 min |
| `small` | ~4.5× realtime | ~6 min |
| `large-v3-turbo` | ~2.7× realtime | ~11 min |

`large-v3-turbo` is the default. Use `small` for a quick first pass.

## What changed from v10, and why

| v10 (Colab) | here | reason |
|---|---|---|
| T4 GPU, `raise RuntimeError` without one | CPU, 16 threads | the entire point |
| `float16` | `int8` | float16 is a GPU compute type |
| whisperx + wav2vec2 alignment | faster-whisper directly | whisperx wraps this same engine and adds an alignment pass that costs more than it returns on CPU; word timestamps come free |
| PyAV decoding | ffmpeg subprocess | see below |
| HF token in a cell | `.env` | v10's token is still live in 7 notebooks |
| venv rebuilt every session | installed once | not a fresh VM each run |
| `.txt` then `.csv` | atomic writes | an interrupt between the two left work paid for but not counted as done |

### The PyAV problem

Smart App Control is enforced on this machine (`VerifiedAndReputablePolicyState = 1`).
It blocks PyAV's bundled DLLs:

```
ImportError: DLL load failed while importing device:
An Application Control policy has blocked this file.
```

faster-whisper imports `av` at module load, so the library is unusable as-is.
`ctranslate2`, `onnxruntime`, `numpy`, and `torch` all load fine — only the
decoder is affected.

`local_transcriber/audio.py` registers a stub `av` module before faster-whisper
is imported, and decodes through ffmpeg into a numpy array instead. `decode_audio`
is the only thing that touches PyAV, and it is never called.

## Metadata

All four v10 layers are preserved:

| Layer | Tool | Extracts |
|---|---|---|
| L1 | ffprobe | `creation_time`, ISO6709 GPS (iOS), `location` tag (Android), codec, bitrate, sample rate |
| L2 | mutagen | MP4 `©xyz` atom, duration, sample rate |
| L3 | exiftool | GPSLatitude/Longitude/Altitude, CreateDate, device Make/Model |
| L4 | file stat | mtime as last resort |

exiftool isn't installed here, so L3 is skipped with a note in the header. L1
already covers iOS and Android GPS, which is where it actually comes from —
Meet, Teams, and Zoom never embed location.

Layer 4 only ever fills gaps. A file's mtime is the weakest possible claim about
when a meeting happened, so it never overwrites a real tag.
