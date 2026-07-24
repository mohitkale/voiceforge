from scripts import download_models


def test_list_mode_reports_manifests_without_running_downloads(monkeypatch, capsys):
    def fail() -> None:
        raise AssertionError("download function must not run in --list mode")

    monkeypatch.setattr(download_models, "ENGINES", {"voxcpm2": fail})
    monkeypatch.setattr("sys.argv", ["download_models.py", "--list"])

    download_models.main()

    output = capsys.readouterr().out
    assert "voxcpm2: experimental" in output
    assert "openbmb/VoxCPM2@9454c2d" in output

