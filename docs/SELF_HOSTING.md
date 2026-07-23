# Self-hosting

Self-hosted by design. Run VoiceForge on your workstation, private server, or
GPU environment. Voice samples and generated audio go only to infrastructure
**you** choose — there is no cloud TTS vendor and no required third-party API
keys for core cloning.

“Self-hosted” is not the same as “physically on your laptop.” A remote GPU VM
you control is still self-hosted; a managed cloud GPU is still **your**
deployment responsibility (auth, TLS, data retention).

## Localhost

```bash
cp .env.example .env
make start-cpu
```

- Studio: http://localhost:8089/
- OpenAPI: http://localhost:8089/docs
- Leaving `VOICEFORGE_API_TOKEN` empty is acceptable **only** for pure localhost
  (the app warns loudly). Never expose an unauthenticated instance.

## LAN

1. Bind/publish port 8089 only on trusted interfaces (compose already maps host 8089).
2. Set a strong `VOICEFORGE_API_TOKEN`.
3. Restrict `VOICEFORGE_CORS_ORIGINS` to known frontends (or keep empty and
   proxy from your backend).
4. Prefer HTTPS via a reverse proxy even on LAN if untrusted devices share the network.

## Private VPS

Same as LAN, plus:

- Firewall: allow only your IPs / VPN where possible
- Reverse proxy (Caddy/nginx/Traefik) with TLS
- Do not commit `.env`, `data/`, or `models/`
- Cap resources (compose `mem_limit` / `cpus` are a starting point)

## GPU cloud / remote GPU

Use the GPU compose profile or a provider guide:

| Guide | Path |
|-------|------|
| Modal | [deploy-modal.md](deploy-modal.md) |
| Lightning | [deploy-lightning.md](deploy-lightning.md) |
| Kaggle (notebooks; limited) | [deploy-kaggle.md](deploy-kaggle.md) |

Always set `VOICEFORGE_API_TOKEN` on any publicly reachable URL. Treat session
disks as sensitive — wipe `data/` before sharing snapshots.

GPU Docker was **not** verified on real NVIDIA hardware during original
development; validate on your host.

## Authentication

| Setting | Behaviour |
|---------|-----------|
| `VOICEFORGE_API_TOKEN` set | Bearer required on `/v1/*` (constant-time compare) |
| Unset | `/v1/*` open — localhost/dev only |
| `/healthz` | No auth (liveness) |

## TLS and reverse proxy

Terminate TLS at the proxy; forward to `127.0.0.1:8089`.

Recommended headers from the proxy: standard security headers; VoiceForge also
adds its own security middleware. Preserve `Authorization` when proxying API
calls.

WebSockets are not required for core API; SSE is used for
`GET /v1/voices/{id}/events` — ensure the proxy does not buffer SSE indefinitely.

## CORS

`VOICEFORGE_CORS_ORIGINS` is an explicit allowlist (comma-separated). Empty =
no browser cross-origin access. Prefer server-side proxies for browser uploads
so tokens stay off the client.

## Persistence

| Data | Typical location |
|------|------------------|
| Voices, SQLite | `./data` bind mount |
| Model weights | Docker volume `models-cache` → `/app/models` |

Back up `data/` if voices matter. Model volumes can be re-downloaded.

## Deletion and retention

- `DELETE /v1/voices/{id}` removes DB row + voice directory
- Rotating a deployment: stop containers, delete `data/voices`, optionally prune volumes
- Operators own retention policy for consent evidence kept outside VoiceForge

## Resource limits

Default CPU service: ~4 CPUs / 6 GB RAM. Heavy engines can OOM — raise limits
deliberately or stick to OpenVoice on small hosts. Concurrent ML jobs are
capped (`VOICEFORGE_MAX_CONCURRENT_JOBS`, default 1).

## Checklist before public exposure

1. Strong API token
2. Tight CORS (or no browser CORS)
3. TLS
4. Non-root Docker (default images)
5. No secrets in git
6. Plan for wiping voice data
7. Review [ENGINE_LICENSING.md](ENGINE_LICENSING.md) for your chosen engines
