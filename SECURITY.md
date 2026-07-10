# Security Policy

## Supported versions

This project is a local-first portfolio / self-hosted service. Security fixes
are applied on the `main` branch.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

Email or privately message the repository maintainer with:

- A short description of the issue
- Steps to reproduce
- Impact (e.g. unauthenticated access, path traversal, model/pickle risk)

## Hardening checklist for public / GPU-cloud deployments

When exposing VoiceForge beyond localhost (VPS, Lightning AI, RunPod, etc.):

1. Set a strong `VOICEFORGE_API_TOKEN` and require `Authorization: Bearer …`
2. Restrict `VOICEFORGE_CORS_ORIGINS` to known frontends (or leave empty and
   proxy only from your backend)
3. Do not commit `.env`, `data/`, or `models/`
4. Prefer the Docker images (non-root user, healthcheck)
5. Treat uploaded reference audio as sensitive — wipe `data/voices/` when done
6. Remember XTTS-v2 weights are **non-commercial (CPML)** — see `NOTICE.md`
