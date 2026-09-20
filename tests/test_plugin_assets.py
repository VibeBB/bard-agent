"""Consistency checks for the bard plugin assets (manifest, frontmatter, links)."""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "bard"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
AGENT_NAMES = {"bard", "bard-critic"}


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    assert m, f"{path} has no YAML frontmatter"
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if re.match(r"^\s", line) or not line.strip():
            continue
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def test_plugin_json() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    for key in ("name", "version", "description", "author", "license"):
        assert manifest.get(key), f"plugin.json missing {key}"
    assert manifest["name"] == "bard"
    assert manifest["license"] == "BSD-3-Clause"


def test_agent_files() -> None:
    agents = sorted(PLUGIN_ROOT.glob("agents/*.md"))
    assert agents, "no agent definitions found"
    names: set[str] = set()
    for path in agents:
        fm = _frontmatter(path)
        assert fm.get("name"), f"{path} frontmatter missing name"
        assert fm.get("description"), f"{path} frontmatter missing description"
        names.add(fm["name"])
    assert names == AGENT_NAMES


def test_skill_files() -> None:
    skills = sorted(PLUGIN_ROOT.glob("skills/*/SKILL.md"))
    assert skills, "no skills found"
    for path in skills:
        fm = _frontmatter(path)
        assert fm.get("name"), f"{path} frontmatter missing name"
        assert fm.get("description"), f"{path} frontmatter missing description"


def test_sing_command() -> None:
    fm = _frontmatter(PLUGIN_ROOT / "commands" / "sing.md")
    assert fm.get("description"), "sing.md frontmatter missing description"


def _markdown_files() -> list[Path]:
    files: list[Path] = []
    for base in (REPO_ROOT / "docs", PLUGIN_ROOT, REPO_ROOT):
        files.extend(sorted(base.glob("*.md")))
        if base != REPO_ROOT:
            files.extend(sorted(base.rglob("*.md")))
    return sorted({p for p in files if p.is_file()})


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: p.name)
def test_relative_links_resolve(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for target in LINK_RE.findall(text):
        if "://" in target or target.startswith("#") or target.startswith("mailto:"):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if not target or target.startswith("<"):
            continue
        resolved = (path.parent / target).resolve()
        assert resolved.exists(), f"{path}: broken link {target}"


def test_sdk_plugin_load() -> None:
    pytest.importorskip("openhands.sdk.plugin")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_plugin_load", REPO_ROOT / "scripts" / "check_plugin_load.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reasons = module.check_plugin(PLUGIN_ROOT)
    assert reasons == [], reasons
