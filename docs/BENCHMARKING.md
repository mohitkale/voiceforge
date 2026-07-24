# Reproducible benchmark harness

The benchmark harness never loads a TTS/ASR model. It creates an immutable run
plan and scores audio/transcripts generated separately by a provider.

The versioned suite is `benchmarks/prompts.v1.jsonl`. It covers English,
Devanagari Hindi, Romanized Hindi, and Hinglish, including questions, names,
numbers, pronunciation, emotion, code-switch boundaries, and long-form
stability.

## 1. Create a plan

```bash
python scripts/benchmark_suite.py plan \
  --provider voxcpm2 \
  --model-revision 9454c2d \
  --hardware "MacBook M-series, 16 GB, macOS version, PyTorch version" \
  --seed 42 \
  --output /tmp/voxcpm2-plan.json
```

The plan embeds every prompt and a deterministic suite SHA-256. Use the same
plan for every provider run.

## 2. Generate observations

Generate one raw WAV per case without loudness normalization. Record one JSON
object per line:

```json
{"case_id":"hi-short-neutral","generated_audio":"/absolute/path/hi.wav","hypothesis":"यह आवाज़ परीक्षण के लिए तैयार है।","latency_seconds":4.2,"peak_memory_mb":7420}
```

`hypothesis` should come from the same pinned ASR for all systems. Optional
human fields are `speaker_similarity`, `emotion_score` (1–5), and `notes`.
Run at least three seeds/takes in separate plans; never cherry-pick the best.

## 3. Score

```bash
python scripts/benchmark_suite.py score \
  --plan /tmp/voxcpm2-plan.json \
  --observations /tmp/voxcpm2-observations.jsonl \
  --output /tmp/voxcpm2-report.json
```

The report includes Unicode-aware WER/CER, duration, peak dBFS, clipping,
latency, real-time factor, memory, speaker similarity, emotion score, and
group summaries. Missing cases are explicit.

## Listening method

- Randomize provider names and output order.
- Keep raw outputs; make separate loudness-matched listening copies.
- Use fluent English/Hindi listeners and a 1–5 score for naturalness,
  intelligibility, pronunciation, speaker similarity, emotion match, and
  code-switch transitions.
- Score fixed-voice/design systems separately from clones.
- Include the real consented reference and one stable baseline.
- Report median, spread, and failure rate—not only mean or best sample.

The older `scripts/benchmark_quality.py` remains a single-file convenience
tool. It may download/load Whisper or Resemblyzer models and is not the
no-model shared harness.
