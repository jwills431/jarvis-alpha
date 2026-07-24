# Handoff prompt for the JARVIS server session

Paste the block below into the Claude app on the server PC to continue the project.

---

I'm continuing a project called JARVIS — a private, fully-local, voice-capable AI
assistant. The code lives in a GitHub repo: https://github.com/jwills431/jarvis-alpha

I'm a relative beginner with command lines, so please:
- Go one step at a time and wait for me to report back before moving on.
- Give exact, copy-pasteable commands and tell me what each one does.
- Explain errors in plain language and never assume I know a tool.
- Use a task list to track progress.

THE FIRST THING TO DO: clone the repo and read these three docs in full, in this
order — they are the source of truth for everything decided so far:
1. docs/JARVIS_SERVER_PLAN.md — the architecture decision and build outline for THIS
   machine (most important).
2. docs/PC_FISH_SESSION.md — the exact, tested Fish/OpenAudio S1-mini install recipe
   and all the gotchas we already hit and solved.
3. docs/HANDOFF.md — the original project background.

THIS MACHINE is the dedicated, always-on JARVIS server (fresh Windows 11 install):
- CPU: AMD Ryzen 7 7800X3D
- GPU: NVIDIA RTX 3060 12 GB (Gigabyte Gaming OC)
- RAM: 64 GB DDR5-6200
- Motherboard: ASUS TUF Gaming A620M-PLUS WIFI (AM5)
- Storage: 2 x 2 TB NVMe (4 TB). PSU: Thermaltake 1200 W Platinum.
- I'm setting it up headless via RDP/SSH — no monitor attached.

THE PLAN (decided last session): run the WHOLE JARVIS stack on this box locally, and
access it from my other devices as a LAN web app. Target layout that fits the 12 GB:
- Fish S1-mini as a compiled, resident worker (~6 GB VRAM) — proven ~60 tok/s /
  ~3x real-time in WSL2 with --compile; quality is great and voice cloning is close.
- Language model (Qwen, ~7-8B, Q4, fully on GPU for low latency) (~5 GB VRAM).
- Whisper (speech-to-text) on the CPU (the 7800X3D handles it), to keep VRAM free.
- 64 GB RAM is the escape hatch for a bigger LLM later via GPU+CPU offload.

BUILD STEPS, in order (please guide me through one at a time):
1. Confirm environment (git, whether WSL2 is present, NVIDIA driver / nvidia-smi).
2. Install WSL2 + Ubuntu; confirm `nvidia-smi` works INSIDE Ubuntu (sees the 3060).
3. Install Fish exactly per docs/PC_FISH_SESSION.md and benchmark it with --compile.
4. Build llama.cpp with CUDA + get the Qwen GGUF model; set up whisper on CPU.
5. Wire JARVIS to talk to the local Fish worker (mirror the resident-Piper worker
   pattern already in jarvis/speech.py).
6. Server-ify: set up HTTPS/TLS (browsers only allow microphone access on localhost
   or HTTPS, so this is required to use JARVIS by voice from my other devices), bind
   the web UI to the LAN, add basic auth, and add a firewall rule limiting access to
   my devices.

KNOWN GOTCHAS (already solved last session — please don't rediscover them):
- Use Python 3.12 for the Fish environment. 3.13 fails (numpy 1.26.4 has no 3.13
  wheel and tries to compile from source).
- NEVER use `uv run` — it silently swaps the CUDA build of PyTorch for the CPU build.
  Always call the environment's Python directly (e.g. `.venv/bin/python`).
- OpenAudio S1-mini is a GATED Hugging Face repo — I must be logged in AND click
  "Agree and access repository" on the model page before downloading.
- Fish code must be pinned to commit d3df505 (branch `s1-mini`); the main branch has
  moved to S2 under a restrictive license. At d3df505 the code is Apache-2.0.
- Keep the Fish code + venv on the Linux filesystem (~/), NOT on a /mnt/... Windows
  path (building a venv there is slow and flaky).

CAUTIONS:
- The Fish "JARVIS" voice is a clone of a real actor's voice — fine for my private,
  offline, non-distributed use, but do NOT help me distribute a cloned voice.
- I haven't chosen a license for JARVIS yet. Fish weights are CC-BY-NC-SA-4.0
  (non-commercial) at the pinned version; Piper is GPL-3.0. Flag implications but
  it's not urgent while the repo is private.
- The big model files (llama.cpp build, Qwen, whisper) are gitignored and must be
  rebuilt/downloaded here with CUDA.

Please start by confirming my environment, then walk me through cloning the repo and
reading those three docs. Then we build, one step at a time.
