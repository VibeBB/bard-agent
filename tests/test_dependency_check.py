"""Tests for scripts/check_dependency_updates.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_dependency_updates.py"


@pytest.fixture(scope="session")
def dep_check() -> Any:
    spec = importlib.util.spec_from_file_location("check_dependency_updates", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_dependency_updates"] = module
    spec.loader.exec_module(module)
    return module


def test_project_dependencies_parsed(dep_check: Any) -> None:
    deps = dep_check.dependency_names(dep_check.project_data(REPO_ROOT))
    assert "openhands-sdk" in deps
    assert "openhands-tools" in deps
    assert "pytest" in deps
    assert "ruff" in deps


def test_lock_versions_cover_direct_deps(dep_check: Any) -> None:
    versions = dep_check.lock_versions(REPO_ROOT)
    deps = dep_check.dependency_names(dep_check.project_data(REPO_ROOT))
    missing = [name for name in deps if name not in versions]
    assert missing == []
    assert versions["openhands-sdk"] == "1.49.5"
    assert versions["pytest"] == "9.1.1"


def test_uv_pin_parsed(dep_check: Any) -> None:
    assert dep_check.uv_version_pin(REPO_ROOT) == "==0.12.18"


def test_workflow_files_have_expected_suffixes(dep_check: Any) -> None:
    files = dep_check.workflow_files(REPO_ROOT)
    assert all(f.suffix in {".yml", ".yaml"} for f in files)


def test_docker_arg_pins_parsed(dep_check: Any) -> None:
    assert dep_check.docker_arg_pins(REPO_ROOT) == {}


def test_docker_base_image_parsed(dep_check: Any) -> None:
    assert dep_check.docker_base_image(REPO_ROOT) == ("ubuntu", "26.04")


def test_render_markdown_groups_by_surface(dep_check: Any) -> None:
    statuses = [
        dep_check.DependencyStatus(
            "pypi", "pydantic", "2.13.5", "2.13.5", "pyproject.toml", False
        ),
        dep_check.DependencyStatus(
            "pypi", "mcp", "1.30.0", "2.2.0", "pyproject.toml", True
        ),
        dep_check.DependencyStatus(
            "docker-base",
            "ubuntu",
            "26.04",
            "26.04",
            "docker/bard-tools.Dockerfile",
            False,
        ),
    ]
    markdown = dep_check.render_markdown(statuses)
    assert "## PyPI (direct dependencies)" in markdown
    assert "## Docker base image" in markdown
    assert "| mcp | 1.30.0 | 2.2.0 | update available | pyproject.toml |" in markdown
    assert "| pydantic | 2.13.5 | 2.13.5 | up to date | pyproject.toml |" in markdown
    assert "update candidates: 1" in markdown


def test_apply_deferrals_marks_matching_outdated(
    dep_check: Any, tmp_path: Path
) -> None:
    deferrals_path = tmp_path / "scripts" / "dependency_update_deferrals.json"
    deferrals_path.parent.mkdir(parents=True)
    deferrals_path.write_text(
        json.dumps(
            {
                "deferrals": [
                    {
                        "surface": "pypi",
                        "name": "mcp",
                        "latest": "2.2.0",
                        "review_by": "2999-01-01",
                        "reason": "test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    deferrals = dep_check.load_deferrals(tmp_path)
    statuses = dep_check.apply_deferrals(
        [
            dep_check.DependencyStatus(
                "pypi", "mcp", "1.30.0", "2.2.0", "pyproject.toml", True
            )
        ],
        deferrals,
        date(2026, 9, 23),
    )
    assert statuses[0].deferred is True
    assert statuses[0].outdated is False
    assert "test" in statuses[0].note
