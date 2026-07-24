# Local Python setup (macOS)

VoiceForge needs **Python 3.11 or 3.12** on your Mac for development,
Mac-native MPS workers, and smoke tests. Docker remains the simplest CPU API/UI
profile, but Linux containers on Docker Desktop cannot use Apple Metal.

If `python` or `pip` show as “command not found”, use this guide.

---

## Quick diagnosis

Open **Terminal** (or Cursor’s terminal) and run:

```bash
echo "$SHELL"
echo "$PATH" | tr ':' '\n' | head -20
which python3 python pip3 pip 2>&1
python3 --version 2>&1
/usr/local/bin/python3 --version 2>&1
```

| Result | Meaning |
|--------|---------|
| `python3` works, `python` does not | Normal on Homebrew macOS — use `python3` / `pip3`, or add aliases below |
| `python3` not found | Homebrew Python not on `PATH` — fix PATH (below) or reinstall |
| Only works inside this repo after `source .venv/bin/activate` | Global PATH broken; venv is fine for this project only |

---

## Fix 1 — PATH (append only, do not replace)

A common mistake is **replacing** `PATH` in `~/.zshrc` with a hard-coded list.
That drops Homebrew paths and breaks `python3`.

**Correct pattern** (append tool dirs to the existing system PATH):

```bash
# ~/.zshrc — append only
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
export PATH="/usr/local/opt/python@3.12/bin:$PATH"
```

**Wrong pattern** (avoid):

```bash
export PATH="/usr/local/bin:/usr/bin:/bin"   # replaces everything else
```

After editing `~/.zshrc`:

```bash
source ~/.zshrc
which python3
python3 --version
```

This repo’s maintainer setup uses Homebrew Python 3.12 at
`/usr/local/opt/python@3.12/bin/python3.12`.

---

## Fix 2 — `python` vs `python3`

Homebrew often installs **`python3`** only, not **`python`**.

Options:

**A. Use explicit names (recommended)**

```bash
python3 --version
pip3 --version
```

**B. Aliases in `~/.zshrc`**

```bash
alias python=python3
alias pip='python3 -m pip'
```

Then: `source ~/.zshrc`

---

## Fix 3 — Reinstall Python via Homebrew (if missing)

If `/usr/local/bin/python3` does not exist:

```bash
brew install python@3.12
brew link python@3.12
echo 'export PATH="/usr/local/opt/python@3.12/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
python3.12 --version
```

Do **not** remove system `/usr/bin/python3` (Apple stub); use Homebrew’s
`python3.12` for development.

---

## VoiceForge project venv

From the repo root (after `python3` works):

```bash
cd /path/to/audio-cloning
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
pytest -q
```

Inside an activated venv, `python` and `pip` work without global aliases.

---

## Fix 4 — `externally-managed-environment` (PEP 668)

Homebrew Python **3.13+** blocks `pip install` outside a venv:

```text
error: externally-managed-environment
```

**Do not** use `--break-system-packages` — it can break Homebrew Python and
weakens isolation.

### Safe options (pick one)

**A. Project venv (recommended for VoiceForge)**

```bash
cd /path/to/audio-cloning
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
```

**B. pipx (optional CLI tools only, separate venv per tool)**

```bash
brew install pipx
pipx ensurepath
source ~/.zshrc   # adds ~/.local/bin
```

**C. Never do this**

Do not use `pip install --break-system-packages ...`.

---

## Security — auditing Python packages

VoiceForge includes `pip-audit` in the dev extra. Run inside the project venv:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pip-audit
```

Fix reported issues by upgrading pinned deps in `requirements*.txt` /
`pyproject.toml`, then re-run tests. Do not install random packages into
system Python.

## Known issues log

| Issue | Fix |
|-------|-----|
| `python: command not found` but `python3` works | Use `python3.12` or add aliases (Fix 2) |
| PATH missing `/usr/local/bin` | Append in `~/.zshrc` (Fix 1); never replace entire PATH |
| `externally-managed-environment` on `pip install` | Use venv or pipx (Fix 4); never `--break-system-packages` |
| Default `python3` is 3.13 | Prefer `python3.12` for this project (see aliases in `~/.zshrc`) |
| `Documents/software/gradle/bin` in PATH without `$HOME` | Use `$HOME/Documents/software/gradle/bin` |
| Duplicate `.venv/bin` repeated in PATH | Remove duplicate `source .venv/bin/activate` from shell startup |
| Cursor terminal differs from Terminal.app | Both read `~/.zshrc` for zsh; run `echo $SHELL` to confirm |

---

## Related docs

- [Deploy on Kaggle](deploy-kaggle.md)
- [Experimental studio](EXPERIMENTAL_STUDIO.md)
- [README Quickstart](../README.md#quickstart-docker)
