# First successful clone

Goal: clone once with **OpenVoice V2** on CPU and hear speech — without
fighting heavier engines on first contact.

## 1. Start VoiceForge (CPU)

```bash
cp .env.example .env
make start-cpu
# equivalent:
# docker compose -f docker/docker-compose.yml --profile cpu up --build
```

Open **http://localhost:8089/** (Studio) or **/docs** (OpenAPI).

After the first build:

```bash
make start-cpu   # or compose up without --build if the image exists
```

## 2. Recommended first engine

Use **`openvoice-v2`** — lightest zero-shot path on CPU and CPU-e2e verified.

Avoid RVC, CosyVoice, IndexTTS, and Fish Speech for your first clone.

## 3. Sample guidance

| Topic | Guidance |
|-------|----------|
| Duration | Prefer ~8+ seconds of clean speech (OpenVoice min ~3s; longer helps) |
| Environment | Quiet room; avoid music, TV, echo |
| Mic distance | ~15–30 cm; steady level; no clipping |
| Content | Natural sentences; clear articulation |
| Formats | `.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`, `.aac` (decoded via libsndfile). Browser `.webm` may fail — prefer WAV |
| Consent | You must confirm you have the right to clone the voice |

Synthetic fixture for automation only:
`scripts/fixtures/f5_reference_en.wav` (not a real person).

## 4. Studio workflow

1. Pick engine `openvoice-v2`
2. Upload or record a sample
3. Confirm consent
4. Start cloning; wait until status is ready (SSE/progress in UI)
5. Enter a short sentence and synthesize
6. Play the result

## 5. API workflow (curl)

```bash
curl -s -X POST http://localhost:8089/v1/voices \
  -F "name=My First Clone" \
  -F "engine_id=openvoice-v2" \
  -F "tier=instant" \
  -F "consent=true" \
  -F "language=en" \
  -F "files=@sample.wav"

curl -s -X POST http://localhost:8089/v1/synthesize \
  -H "Content-Type: application/json" \
  -d '{"voiceId":"<id>","text":"Hello from VoiceForge."}' \
  -o out.wav
```

If `VOICEFORGE_API_TOKEN` is set, add `Authorization: Bearer …`.

Smoke helper:

```bash
make smoke-openvoice
```

## 6. First-run expectations

| Event | Expectation |
|-------|-------------|
| First model download | Can take several minutes; weights land in the `models-cache` Docker volume |
| First synthesis | Slower (cold load); later requests faster while the process is warm |
| Host impact | Compose defaults cap ~4 CPUs / 6 GB RAM for the CPU service |

Optional pre-download:

```bash
docker compose -f docker/docker-compose.yml --profile cpu run --rm voiceforge-download
```

## 7. Where files live

| Path | Contents |
|------|----------|
| `./data/` (bind mount) | SQLite DB, `voices/{id}/samples`, `artifacts`, `preview.wav` |
| Docker volume `models-cache` | Downloaded checkpoints |

## 8. Delete a voice completely

```bash
curl -X DELETE http://localhost:8089/v1/voices/<id>
```

Removes DB metadata and the on-disk voice directory (samples + artifacts).

## 9. Stop and remove Docker resources

```bash
make stop
# Remove containers/networks for this compose project; keep volumes unless you prune:
docker compose -f docker/docker-compose.yml --profile cpu down

# Destructive — deletes model cache and (if you also remove bind data) local voices:
# docker volume rm <models-cache-volume-name>
# rm -rf data/voices data/voiceforge.sqlite3
```

## 10. Common failures

| Symptom | What to try |
|---------|-------------|
| `503` engine not ready | Wait for download; run `voiceforge-download`; check `/v1/engines` |
| `422` consent | Send `consent=true` |
| `422` tier on RVC | Use `tier=high_fidelity` (not for first clone) |
| Invalid audio | Re-export as WAV; ensure real audio bytes |
| Host thrashing | Keep resource limits; use OpenVoice; close other heavy apps |
| Token 401 | Match `VOICEFORGE_API_TOKEN` or leave empty for pure localhost |

More: [SELF_HOSTING.md](SELF_HOSTING.md), [ENGINES.md](ENGINES.md), [RESPONSIBLE_USE.md](../RESPONSIBLE_USE.md).
