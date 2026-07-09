from __future__ import annotations

import run


def test_web_mode_detects_web_flag():
    assert run._is_web_mode(["run.py", "--web"]) is True


def test_web_mode_detects_short_web_flag():
    assert run._is_web_mode(["run.py", "-w"]) is True


def test_web_mode_false_without_flag():
    assert run._is_web_mode(["run.py"]) is False


def test_kill_port_does_not_use_windows_commands_on_macos(monkeypatch):
    run_calls = []
    check_output_calls = []

    monkeypatch.setattr(run.sys, "platform", "darwin")
    monkeypatch.setattr(run.subprocess, "check_output", lambda *args, **kwargs: check_output_calls.append(args))

    def fake_run(*args, **kwargs):
        run_calls.append((args, kwargs))

        class Result:
            stdout = ""

        return Result()

    monkeypatch.setattr(run.subprocess, "run", fake_run)

    run._kill_port(8000)

    assert check_output_calls == []
    assert run_calls[0][0][0] == ["lsof", "-ti", f"tcp:{8000}", "-sTCP:LISTEN"]


def test_setup_runs_when_chromium_missing():
    assert run._should_run_setup(lambda: False, lambda: True) is True


def test_setup_runs_when_ffmpeg_missing_even_if_chromium_ready():
    assert run._should_run_setup(lambda: True, lambda: False) is True


def test_setup_skips_when_all_dependencies_ready():
    assert run._should_run_setup(lambda: True, lambda: True) is False
