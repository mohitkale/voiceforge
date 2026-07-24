# Kaggle / Colab GPU smoke tests

Kaggle and Google Colab are useful for short, no-cost GPU experiments. They
are not VoiceForge hosting targets: sessions, accelerator availability, disk,
internet access, and quotas change without notice.

Use a fresh notebook, one provider at a time, and only your own or explicitly
permitted reference audio. Do not start a public tunnel.

## Safe workflow

1. Select a GPU runtime and record the reported GPU, Python, PyTorch, and CUDA
   versions in the benchmark plan.
2. Upload or clone VoiceForge at a known commit.
3. Create a provider-specific environment and install only its pinned
   requirements. Do not mix Chatterbox, VoxCPM2, Qwen3-ASR, and the main
   VoiceForge environment.
4. Review the official model card and licence, then explicitly download the
   manifest’s immutable revision into notebook-local storage.
5. Point the worker at that local directory. Never pass a model ID to an
   inference worker and never enable `trust_remote_code`.
6. Run one job at a time. Save benchmark JSON/audio only if needed, then delete
   reference audio and outputs or reset the runtime.

The exact setup and current immutable revisions are in
[Experimental studio](EXPERIMENTAL_STUDIO.md), while the provider-independent
measurement method is in [Benchmarking](BENCHMARKING.md).

## Minimal environment

After checking out the repository at a known commit:

```python
import os

os.environ["VOICEFORGE_DEVICE"] = "cuda"
os.environ["VOICEFORGE_HOST"] = "127.0.0.1"
os.environ["VOICEFORGE_MAX_CONCURRENT_JOBS"] = "1"
os.environ["VOICEFORGE_DATA_DIR"] = "/kaggle/working/voiceforge-data"
os.environ["VOICEFORGE_MODELS_DIR"] = "/kaggle/working/voiceforge-models"
```

Use `/content/...` paths on Colab. Install exactly one of:

```bash
python -m pip install -r requirements-voxcpm2.txt
# or, in a separate fresh runtime:
python -m pip install -r requirements-qwen3-asr.txt
# or, in a separate fresh runtime:
python -m pip install -r requirements-chatterbox.txt
```

The application does not fetch weights during startup. Model setup is a
separate, explicit action:

```bash
python scripts/download_models.py --engine voxcpm2
# or: qwen3-asr / chatterbox
```

This action requires internet access and consumes several gigabytes. Inspect
the manifest with `python scripts/download_models.py --list` first.

## Run without exposure

Prefer direct worker/benchmark calls. If API testing is necessary, bind only
to the notebook loopback interface:

```bash
VOICEFORGE_ENABLED_ENGINES=voxcpm2 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8089
```

Call `http://127.0.0.1:8089` from another notebook cell. Do not use ngrok,
Cloudflare Tunnel, Gradio sharing, or a notebook proxy.

## Recommended order

| Provider | Role | Notebook status |
|---|---|---|
| `voxcpm2` | Hindi/English TTS and reference cloning | First experimental GPU candidate |
| `chatterbox` | Multilingual V3 clone, including Hindi | Isolated worker; benchmark after VoxCPM2 |
| `qwen3-asr` | Reference transcription; optional alignment | Useful evaluator; Hindi transcription verified |
| `qwen3-tts` | High-quality multilingual clone | No Hindi claim; test supported languages only |
| `indicf5` | Indic clone candidate | Manifest-only; gated and remote-code review required |
| `indic-parler-tts` | Indic expressive/design candidate | Manifest-only; gated |

Qwen3-ASR’s official forced aligner does not list Hindi. Use it for Hindi
transcription only, not Hindi word timestamps.

## Smoke threshold

Start with one short prompt in each applicable group: English, Hindi
Devanagari, Romanized Hindi, and Hinglish. Record latency, peak GPU memory,
failure/OOM status, audio duration, and whether the output is intelligible.
Only run the full versioned suite after the provider passes this smoke test.
