# Roadmap

Milestones **M0–M8** described below are complete in this repository (M6 client
integration lives in apps such as Reel Studio). Future work is listed under
**Next**.

## Project status (user-facing)

**Early public release.** The local Studio, API, engine registry, Docker setup,
and supported cloning workflows are available. Engine installation, quality, and
hardware requirements vary. Some integrations still need broader hardware
testing (especially GPU paths).

## Completed milestones

- [x] **M0 — Scaffold:** FastAPI skeleton, `/healthz`, SQLite, Docker CPU image,
      engine registry, README.
- [x] **M1 — MVP clone (XTTS-v2):** upload → instant zero-shot → `/synthesize` WAV.
- [x] **M2 — Quality benchmarking:** `scripts/benchmark_quality.py`, reference
      preprocessing.
- [x] **M3a — F5-TTS engine:** permissive-license zero-shot behind `CloneEngine`.
- [x] **M3b — OpenVoice V2 engine:** MIT-oriented zero-shot path behind `CloneEngine`.
- [x] **M4 — High-fidelity tier:** RVC isolated worker, SSE progress, upgrade API.
- [x] **M5 — Docker hardening:** CPU/GPU images, model cache, e2e smoke
      (CPU verified for openvoice-v2, xtts-v2, f5-tts).
- [x] **M6 — Reel Studio integration:** client-side `VoiceProvider` + clone UI
      (in the client repo).
- [x] **M7 — Polish:** CI, structured logging, metrics, optional watermark,
      OpenAPI polish, NOTICE/SECURITY.
- [x] **M8 — Additional engines:** Chatterbox, Qwen3-TTS, Fish Speech sidecar,
      CosyVoice 3, IndexTTS2, architecture SVGs.

## Next

- [ ] Broader GPU hardware verification for RVC / heavy engines
- [ ] Optional consent metadata fields (source/note/intended use) if needed
- [ ] Cross-platform launcher (`./voiceforge start --cpu`) if demand warrants
- [ ] Additional watermark robustness tests (recompression) — documentation-only until measured
- [ ] Community-contributed engine adapters with licence review via issue template

See also [docs/ENGINES.md](docs/ENGINES.md) for readiness labels.
