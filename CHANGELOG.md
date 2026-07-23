# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Open-source launch documentation: responsible use, consent, engines matrix,
  licensing matrix, first-clone guide, self-hosting, Reel Studio notes,
  watermarking docs, demo capture process, contributor/community templates.
- Makefile helpers: `start-cpu`, `start-gpu`, `stop`, `logs`, `smoke-openvoice`.
- Studio consent checkbox; Studio loads engines/voices without a token when the
  API is open (localhost); default engine highlight for `openvoice-v2`.
- Authentic Studio screenshot and engine-comparison diagram under `docs/assets/`.

### Fixed

- CI Ruff failures (`S110` / import order) in ASR and Chatterbox paths.

## [0.3.0] — 2026-07-10

### Added

- Additional clone engines (Chatterbox, Qwen3-TTS, Fish Speech sidecar,
  CosyVoice 3, IndexTTS2).
- Studio web UI with in-browser recording.
- Modal deploy path and deployment guides.
- SVG architecture / clone-flow diagrams.

## [0.2.0] — earlier

### Added

- GitHub CI, structured logging, `/v1/metrics`, optional synth watermark,
  OpenAPI polish, NOTICE.md / SECURITY.md.
- RVC high-fidelity worker, F5-TTS, OpenVoice V2, Docker model pre-download,
  CPU e2e smoke tests.

## [0.1.0] — earlier

### Added

- Initial FastAPI service, XTTS-v2 cloning, secured API, Docker CPU/GPU images.
