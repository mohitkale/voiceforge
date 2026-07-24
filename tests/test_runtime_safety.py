from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_is_localhost_only_and_drops_capabilities():
    compose = (ROOT / "docker/docker-compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8089:8089"' in compose
    assert '\n    - "8089:8089"' not in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose
    assert "pids_limit:" in compose


def test_compose_has_no_mutable_fish_image():
    compose = (ROOT / "docker/docker-compose.yml").read_text(encoding="utf-8")

    assert "image: fishaudio/" not in compose
    assert "latest-server" not in compose.replace("`latest-server-cpu`", "")
