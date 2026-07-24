from app.engines.subprocess_env import sanitized_subprocess_env, worker_exec_command


def test_forces_pythonhashseed_zero(monkeypatch):
    monkeypatch.setenv("PYTHONHASHSEED", "not-a-number")
    env = sanitized_subprocess_env()
    assert env["PYTHONHASHSEED"] == "0"
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"


def test_worker_exec_command_uses_env_on_unix():
    from pathlib import Path

    cmd = worker_exec_command(
        Path("/opt/chatterbox-venv/bin/python"),
        Path("/root/scripts/chatterbox_worker.py"),
        ["ping"],
    )
    assert cmd[0] == "/usr/bin/env"
    assert cmd[1] == "PYTHONHASHSEED=0"
    assert cmd[2].endswith("python")
