# CPU versus Vega Metal benchmark

Date: July 18, 2026
Host: Intel iMac Pro, 10-core 3 GHz Xeon W, Radeon Pro Vega 64 16 GB, 128 GB RAM
Runtime: llama.cpp release `b10066`, commit `86a9c79`, AppleClang 17, Metal enabled
Model: Qwen2.5-7B-Instruct GGUF `Q4_K_M`, 7.62B parameters, 4,677,120,000 bytes
Merged-model SHA-256: `1875fb29e8c91c86615c00e92d8b4114e56bc24359adb5a8db8b36452fae4a49`

## Controlled result

The matched comparison used 10 threads, batch 256, micro-batch 64, 64 prompt tokens, 16 generated tokens, and three repetitions.

| Backend | Prompt tokens/s | Generation tokens/s | Result |
|---|---:|---:|---|
| CPU + Accelerate | 61.54 ± 0.63 | 13.63 ± 0.54 | Selected |
| Vega 64 Metal, full offload | 4.03 ± 0.005 | 3.01 ± 0.014 | Rejected |

Metal was about 15 times slower for prompt processing and 4.5 times slower for generation. The default larger Metal batch also failed prompt decoding, while the conservative batch completed reliably.

An additional live CPU request measured approximately 68 prompt tokens/s and 15.8 generation tokens/s for a short response.

## Decision

The alpha defaults to `JARVIS_GPU_LAYERS=0`. Metal remains compiled in for future regression tests, but must not be enabled for normal use unless a newer pinned llama.cpp release materially changes these results.

Raw benchmark results are locally retained under the ignored `benchmark/results/` directory because upstream output includes a private absolute model path.

## Rolling-context cache benchmark

The reliability pass also compared the same synthetic 19-message rolling-history workload before and after enabling llama.cpp cache reuse. The first request was intentionally a full prompt evaluation; the second shifted the bounded history window by one complete turn.

| Setting | First request | Shifted request | Shifted prompt tokens evaluated |
|---|---:|---:|---:|
| Default (`cache-reuse=0`) | 21.75 s | 16.98 s | 1,314 |
| Selected (`cache-reuse=64`) | 21.83 s | 1.78 s | 46 |

Both selected-setting responses were complete and untruncated. The shifted request was approximately 89.5% faster than the no-reuse baseline, so the alpha now defaults to `JARVIS_CACHE_REUSE=64`. Set `JARVIS_CACHE_REUSE=0` before `scripts/start.sh` to restore the previous behavior. This optimization accelerates overlapping recent context; it does not enlarge the 20-message/12,000-character context contract or create persistent memory.
