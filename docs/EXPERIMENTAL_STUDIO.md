# Experimental studio: Mac first, free GPU second

VoiceForge is a local experimentation service, not a paid-provider gateway.
Experimental providers are disabled by default and never install dependencies,
download weights, or start model workers during application startup.

`GET /v1/providers` is the source of truth for model revisions, licences,
integration state, and Mac/Docker/notebook support. Short commit revisions in
the manifests are immutable Hugging Face revisions, not `main`.

## Safety rules

1. Use only your own voice or audio with explicit permission.
2. Use one provider per isolated virtual environment or container.
3. Download a reviewed, pinned snapshot explicitly; then point VoiceForge at
   its local directory. Do not give workers a model ID.
4. Bind services to `127.0.0.1`, keep CORS empty, and do not use tunnels.
5. Run one heavy job at a time. Stop if macOS memory pressure, swap, or
   temperature becomes excessive.
6. Delete notebook outputs and voice references after testing.

## Mac-native profile

Native Python is required for Metal/MPS. Docker Desktop cannot expose Apple
Metal to Linux containers.

Create a dedicated environment per provider:

```bash
python3.12 -m venv .venv-voxcpm2
source .venv-voxcpm2/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-voxcpm2.txt
```

Download the pinned snapshot only after reviewing its model card:

```bash
# Run from the main VoiceForge development environment, not app startup.
python scripts/download_models.py --engine voxcpm2
```

Opt in explicitly:

```bash
export VOICEFORGE_HOST=127.0.0.1
export VOICEFORGE_DEVICE=mps
export VOICEFORGE_ENABLED_ENGINES=voxcpm2
export VOICEFORGE_VOXCPM2_PYTHON="$PWD/.venv-voxcpm2/bin/python"
export VOICEFORGE_VOXCPM2_MODEL_DIR="$PWD/models/voxcpm2"
```

VoxCPM2 is experimental on Mac. Upstream advertises MPS, but model size and
operator compatibility vary by Mac/PyTorch release. The current worker exposes
reference cloning and optional style text. Upstream voice design is recorded
in the manifest; a sample-free VoiceForge design workflow remains roadmap work.

Chatterbox Multilingual V3 follows the same pattern with
`requirements-chatterbox.txt`, `VOICEFORGE_CHATTERBOX_PYTHON`, and
`VOICEFORGE_CHATTERBOX_MODEL_DIR`. The worker uses
`ChatterboxMultilingualTTS`, `language_id`, and local `v3` weights. One request
has one language ID; mixed-language Hinglish is a benchmark target, not a
guaranteed capability.

Qwen3-TTS now maps explicit/automatic MPS to `mps`, never `cuda:0`, but upstream
MPS quality and performance are not verified. Treat it as an experimental Mac
path and use its pinned model revision. It is not ready unless
`VOICEFORGE_QWEN3_TTS_MODEL_DIR` points to a local snapshot; model IDs are not
passed to the runtime loader.

## Qwen3-ASR reference intelligence

Qwen3-ASR is separate from clone engines. It can replace Whisper for reference
transcription after explicit opt-in:

```bash
python3.12 -m venv .venv-qwen3-asr
source .venv-qwen3-asr/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-qwen3-asr.txt

# Explicitly downloads both pinned local snapshots.
python scripts/download_models.py --engine qwen3-asr

export VOICEFORGE_REFERENCE_ASR_PROVIDER=qwen3-asr
export VOICEFORGE_QWEN3_ASR_PYTHON="$PWD/.venv-qwen3-asr/bin/python"
export VOICEFORGE_QWEN3_ASR_MODEL_DIR="$PWD/models/qwen3-asr-0.6b"
export VOICEFORGE_QWEN3_ALIGNER_MODEL_DIR="$PWD/models/qwen3-forced-aligner-0.6b"
```

Transcription includes Hindi. The official forced aligner supports eleven
languages and does **not** include Hindi, so Hindi alignment must remain
disabled until upstream adds it or a reviewed alternative is integrated.

## Docker CPU profile

```bash
docker compose -f docker/docker-compose.yml --profile cpu up --build
```

Compose publishes `127.0.0.1:8089` only, drops Linux capabilities, applies
process/CPU/memory limits, and runs as a non-root user. It is appropriate for
API/UI and small CPU smoke tests. It cannot benchmark MPS.

The Fish Speech mutable image was removed. If testing Fish, run a separately
reviewed digest-pinned sidecar on a private Docker network and opt in with
`VOICEFORGE_FISH_SPEECH_URL`. Current Fish weights are research/noncommercial,
and VoiceForge no longer advertises an unverified Hindi language list.

## Colab or Kaggle smoke profile

Free notebook capacity and GPU types change. Record the actual device and do
not treat a notebook as hosting.

1. Start a fresh runtime; upload/clone the repository at a known commit.
2. Install one provider’s pinned requirements only.
3. Download one immutable model revision into notebook-local storage.
4. Set `VOICEFORGE_DEVICE=cuda`, an engine allowlist containing one provider,
   and `VOICEFORGE_MAX_CONCURRENT_JOBS=1`.
5. Run benchmark generation inside the notebook process or bind Uvicorn only
   to `127.0.0.1`. Do not create Gradio/ngrok/Cloudflare/public tunnels.
6. Run a short English/Hindi/Hinglish smoke subset, record GPU/VRAM and errors,
   then reset the runtime and delete outputs.

IndicF5 and Indic Parler-TTS appear as `manifest-only`, gated experiments.
VoiceForge does not install or execute them. IndicF5’s upstream example uses
remote model code; integration requires a separate review and immutable local
worker before enablement.

## Roadmap

1. Run the no-model contract/unit suite on every change.
2. Benchmark existing external Kokoro output as a fixed-voice baseline only
   after the user supplies the actual implementation/source location.
3. Mac smoke: Chatterbox V3, then VoxCPM2, one local snapshot at a time.
4. Free GPU smoke: VoxCPM2 and Qwen3-ASR; compare against IndicF5/Indic Parler
   only after accepting their gates and reviewing runtime code.
5. Add a sample-free designed-voice resource/API before claiming that
   VoiceForge exposes VoxCPM2 voice design end to end.
6. Promote an experimental provider only after reproducible English, Hindi,
   Romanized Hindi, and Hinglish results plus licence review.

## Primary sources

- [VoxCPM2 repository](https://github.com/OpenBMB/VoxCPM)
- [Qwen3-ASR repository](https://github.com/QwenLM/Qwen3-ASR)
- [Qwen3-TTS repository](https://github.com/QwenLM/Qwen3-TTS)
- [Chatterbox repository](https://github.com/resemble-ai/chatterbox)
- [IndicF5 model card](https://huggingface.co/ai4bharat/IndicF5)
- [Indic Parler-TTS model card](https://huggingface.co/ai4bharat/indic-parler-tts)
