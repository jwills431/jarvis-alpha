# PC session — Fish/OpenAudio S1-mini evaluation

Working note from the Windows PC session, 2026-07-22. Companion to `HANDOFF.md`.
Fold into `HANDOFF.md` when convenient. This captures the reproducible Fish setup
and the go/no-go verdict so work can resume after a reboot or in a new session.

## The PC (verified this session)

- Windows 11, git 2.55, system Python 3.11.9.
- WSL2 feature present but **no distro installed** yet.
- GPU is actually an **RTX 4060 Ti, 8 GB** — not the 4070 Ti / 12 GB the handoff
  assumed. Driver 596.21, CUDA 13.2. 8 GB turned out to be enough (see benchmark).

## Fish install that works (native Windows), in `D:\Claude\JARVIS AI\fish-speech`

- **Version pin matters.** OpenAudio S1-mini is not a clean release tag. The
  fish-speech `main` branch has moved on to S2 under a restrictive license.
  Checked out commit **`d3df505`** as branch **`s1-mini`** — the last pure-S1
  state before S2. At that commit the code is **Apache-2.0**, model weights are
  **CC-BY-NC-SA-4.0 (non-commercial)**, and the tools default to loading
  `checkpoints/openaudio-s1-mini`.
- **Install with uv, forcing Python 3.12:**
  `uv sync --extra cu128 --python 3.12`
  (Python 3.13 fails: numpy 1.26.4 has no 3.13 wheel, tries to source-build with
  MSVC, and that also tripped Avast. 3.12 uses prebuilt wheels — clean.)
- **Gotcha — never use `uv run`.** It re-syncs the env every call and swaps the
  CUDA build of torch for the CPU build (`torch.cuda.is_available()` -> False).
  Always call the env's Python directly:
  `.\.venv\Scripts\python.exe ...`  (installed torch 2.8.0+cu128).
- **Model is a gated HF repo.** Must be logged in AND click "Agree and access
  repository" on https://huggingface.co/fishaudio/openaudio-s1-mini (redirects to
  `fishaudio/s1-mini`). Then:
  `.\.venv\Scripts\hf.exe download fishaudio/openaudio-s1-mini --local-dir checkpoints\openaudio-s1-mini`
  Downloads ~3.6 GB: `model.pth` (1.74 GB) + `codec.pth` (1.87 GB) + config/tokenizer.
- **Hear it:** `.\.venv\Scripts\python.exe -m tools.run_webui` then open
  http://127.0.0.1:7860. Empty reference = stock voice; a 10-30 s reference clip
  = voice clone. Ctrl+C to stop and free the GPU.

## Benchmark verdict — native Windows, no `--compile`

- ~8 tok/s. A ~4.5 s sentence took ~12 s (stock) / ~16 s with voice cloning.
  That's ~2.5-3x slower than real-time — too slow for conversation.
- Fit in 6.6 GB VRAM even while cloning, so 8 GB is fine.
- **Quality: impressive. The reference-clip clone was "pretty close" to target.**
  Decision: worth building around.
- The slowness is the expected no-`--compile` floor (Triton is Linux-only).
  `--compile` claims ~10x, which would put a sentence near ~1-1.5 s.

## WSL2 setup DONE + compile benchmark (2026-07-22)

- Installed WSL2 + Ubuntu (`wsl --install -d Ubuntu`, no reboot needed). GPU
  passes through to WSL automatically via the Windows driver — `nvidia-smi` works
  inside Ubuntu, no CUDA toolkit install required for PyTorch.
- Apt prereqs: `build-essential git curl ffmpeg libsndfile1 portaudio19-dev`
  (build-essential is what makes `--compile` work — the compiler Windows lacked).
- Fish code + venv live on the **Linux filesystem** at `~/jarvis/fish-speech`
  (NOT on /mnt/d — building a venv on the Windows mount is slow/flaky). Model
  files reused via symlink: `ln -s "/mnt/d/Claude/JARVIS AI/fish-speech/checkpoints" checkpoints`.
- Same install: `uv sync --extra cu128 --python 3.12`; run with `.venv/bin/python`
  (never `uv run`). Launch: `.venv/bin/python -m tools.run_webui --compile`.
- torch.compile just worked — no extra CUDA toolkit needed. First generation per
  process is a one-time ~3-7 s compile; then warm.

**Warm benchmark (WSL2 + --compile, RTX 4060 Ti 8 GB):**
- Stock voice: **~59 tok/s**. Cloned voice (24 s reference): **~60 tok/s** — cloning
  is free at speed. ~13 s of speech generated in ~4.7 s = **~3x faster than real-time**.
- GPU memory ~5.2 GB stock / ~6.7 GB cloned — fits 8 GB fine.
- vs native Windows (no compile) ~6-8 tok/s: about an **8x speedup**. Matches Fish's
  ~10x claim. Verdict: fast enough for conversation, quality impressive. GO.

## Next: decide architecture (OPEN — task 4)

1. **Move the whole JARVIS stack to the PC.** Fully local + loopback-only preserved;
   the 4060 Ti also accelerates llama.cpp + whisper. Most work, cleanest fit.
   (Note: `config.py`/`speech.py` assume POSIX venv layout — revisit for Windows,
   or run JARVIS itself inside WSL.)
2. **Fish as a LAN service on the PC, JARVIS stays on the Mac.** Fastest to stand up,
   but crosses the loopback-only boundary (reply text leaves the Mac).

To resume the Fish voice in WSL next session:
`cd ~/jarvis/fish-speech && .venv/bin/python -m tools.run_webui --compile`
then open http://127.0.0.1:7860.

## Still open (unchanged from HANDOFF)

- License for JARVIS itself. Note Fish adds a CC-BY-NC-SA-4.0 (non-commercial)
  weight license at the pinned version — relevant if JARVIS ever goes commercial.
- Model files are gitignored; they live only on the PC's D: drive now.
