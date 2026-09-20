"""Shared fixtures: load render_song.py as a module from its plugin path."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "plugins"
    / "bard"
    / "skills"
    / "bard-render"
    / "scripts"
    / "render_song.py"
)
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def render_module() -> Any:
    spec = importlib.util.spec_from_file_location("render_song", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_song"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def valid_en() -> dict[str, Any]:
    return json.loads((FIXTURES / "valid_en.json").read_text(encoding="utf-8"))


@pytest.fixture()
def valid_ja() -> dict[str, Any]:
    return json.loads((FIXTURES / "valid_ja.json").read_text(encoding="utf-8"))
