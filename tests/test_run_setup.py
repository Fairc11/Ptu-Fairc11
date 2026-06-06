from __future__ import annotations

import run


def test_setup_runs_when_chromium_missing():
    assert run._should_run_setup(lambda: False, lambda: True) is True


def test_setup_runs_when_ffmpeg_missing_even_if_chromium_ready():
    assert run._should_run_setup(lambda: True, lambda: False) is True


def test_setup_skips_when_all_dependencies_ready():
    assert run._should_run_setup(lambda: True, lambda: True) is False
