"""Pytest configuration shared by all tests."""

import os
from pathlib import Path


def pytest_configure(config):
    """Keep tmp_path inside the project and isolate concurrent/repeated runs."""
    if config.option.basetemp is None:
        temp_root = Path("instance") / "pytest-runs"
        temp_root.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = temp_root / str(os.getpid())
