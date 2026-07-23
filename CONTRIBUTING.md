# Contributing

Thanks for helping improve VoiceForge.

## Before you start

1. Read [RESPONSIBLE_USE.md](RESPONSIBLE_USE.md) and [docs/CONSENT.md](docs/CONSENT.md).
2. Read [docs/ENGINE_LICENSING.md](docs/ENGINE_LICENSING.md) — do not imply all
   models are commercially usable.
3. Do not commit voice samples of real people, API tokens, `.env`, or `data/`.

## Development setup

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check app tests scripts
```

ML engines are optional for unit tests (a `FakeEngine` covers API layers).

## Pull requests

- Keep changes focused; prefer docs/engine adapters in separate PRs when large.
- Run `ruff check app/ scripts/ tests/` and `pytest tests/ -q` before pushing.
- Do not add telemetry, cloud TTS vendors, or analytics.
- New engines: implement `CloneEngine`, register in `app/engines/registry.py`,
  document readiness and licences (use the engine-request issue template).

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Security

See [SECURITY.md](SECURITY.md). Report vulnerabilities privately — never attach
private audio or tokens to public issues.
