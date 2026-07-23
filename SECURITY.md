# Security Policy

## Supported versions

Security fixes are applied on the `main` branch of this self-hosted service.

## Reporting a vulnerability

**Do not** open a public GitHub issue for security-sensitive reports.

Contact the repository maintainer privately with:

- A short description of the issue
- Steps to reproduce
- Impact (e.g. unauthenticated access, path traversal, model/pickle risk)

**Do not attach:** private voice samples, API tokens, unredacted databases, or
consent evidence containing personal data.

## Voice data incidents

Treat uploaded reference audio and generated speech as sensitive. If a
deployment leaks `data/` or tokens, rotate credentials, wipe affected voice
directories, and notify affected operators/users as appropriate.

## Hardening checklist for public / GPU-cloud deployments

When exposing VoiceForge beyond localhost (VPS, Lightning AI, RunPod, Modal, etc.):

1. Set a strong `VOICEFORGE_API_TOKEN` and require `Authorization: Bearer …`
2. Restrict `VOICEFORGE_CORS_ORIGINS` to known frontends (or leave empty and
   proxy only from your backend)
3. Terminate TLS at a reverse proxy
4. Do not commit `.env`, `data/`, or `models/`
5. Prefer the Docker images (non-root user, healthcheck, resource limits)
6. Wipe `data/voices/` when done or when permission ends
7. Remember model licences vary — especially XTTS-v2 **CPML non-commercial** —
   see `NOTICE.md` and `docs/ENGINE_LICENSING.md`

More: [docs/SELF_HOSTING.md](docs/SELF_HOSTING.md), [RESPONSIBLE_USE.md](RESPONSIBLE_USE.md).
