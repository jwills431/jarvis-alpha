# Architecture decision — dedicated JARVIS server

Decided 2026-07-22. Supersedes the open "architecture fork" in `HANDOFF.md` and
`PC_FISH_SESSION.md`. Companion to those docs.

## Decision

Run the **whole JARVIS stack on a dedicated always-on box**, accessed from other
devices as a **LAN web app**. Not the gaming PC (keeps it free), and not the
split "Fish-as-a-service" option (which would scatter components across machines).

## The server (hardware — already owned)

- CPU: **Ryzen 7 7800X3D** (great inference CPU, large cache)
- GPU: **RTX 3060 12 GB** (Gigabyte, Gaming OC)
- RAM: **64 GB** DDR5-6200 (headroom for a bigger LLM via GPU+CPU split)
- Board: ASUS TUF Gaming A620M-PLUS WIFI (A620, AM5) — single PCIe 4.0 x16 for GPU,
  fine for a single-GPU server
- Storage: 2 x 2 TB NVMe (4 TB)
- Cooling: Corsair H100i AIO. PSU: Thermaltake 1200 W Platinum (huge headroom)
- OS: Windows 11 (fresh reset)

Why it beats the gaming PC (7900X / RTX 4060 Ti 8 GB) as the host: +50% VRAM, 64 GB
RAM, it's being freed up anyway, and it leaves the gaming rig untouched.

## Target component / VRAM layout (fits 12 GB)

- **Fish S1-mini** — compiled *resident worker* (compile once at startup, then warm
  ~60 tok/s / ~3x real-time): ~6 GB VRAM.
- **LLM (Qwen, 7-8B, Q4, fully on GPU for low latency)**: ~5 GB VRAM. Total ~11 GB.
- **Whisper (STT) on the CPU** (whisper.cpp on the 7800X3D) to keep VRAM free.
- 64 GB RAM is the escape hatch for a larger LLM later via partial GPU offload.

## Build outline (reuse the recipe in PC_FISH_SESSION.md)

1. WSL2 + Ubuntu on the server; confirm `nvidia-smi` in WSL sees the 3060.
2. Fish: same install (`d3df505`, `uv sync --extra cu128 --python 3.12`, run with
   `.venv/bin/python`, `--compile`). Point at the S1-mini weights.
3. llama.cpp built with CUDA + the Qwen GGUF; whisper (CPU) — the gitignored
   runtimes to re-provision.
4. Wire JARVIS to talk to the local Fish worker (mirror the existing resident-Piper
   worker pattern in `jarvis/speech.py`).
5. **TLS / HTTPS** — required so browsers on *other* devices will grant microphone
   access (getUserMedia only works on localhost or HTTPS). Self-signed cert or a
   small local CA.
6. Bind the web UI to the LAN (0.0.0.0), add **basic auth**, and a **firewall rule**
   limiting access to your devices. This crosses the loopback-only design line, but
   all processing stays on the one box (nothing leaves to the cloud).

## Open items

- License: still unsettled. Fish adds CC-BY-NC-SA-4.0 (non-commercial) weights at the
  pinned S1 version; Piper is GPL-3.0. Relevant before the repo goes public/commercial.
- `config.py`/`speech.py` assume POSIX venv layout — clean if JARVIS runs inside WSL.
- Exact LLM size/quant to balance quality vs the ~5 GB GPU budget (or lean on 64 GB
  RAM for a bigger model with offload).
- The gaming-PC 4060 Ti Fish install was the throwaway proof-of-concept; the server
  gets a fresh build from the documented recipe.
