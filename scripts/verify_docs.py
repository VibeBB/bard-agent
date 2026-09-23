"""Verify Markdown links, the ADR index, and the README SDK pin."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SKIP_PARTS = {".git", ".venv", "node_modules", "out"}
SDK_DECL_PATTERN = re.compile(r"OpenHands Software Agent SDK v(\d+\.\d+\.\d+)")
SDK_PIN_PATTERN = re.compile(r"^openhands-sdk==(\d+\.\d+\.\d+)$")


def check_links() -> list[str]:
    errors: list[str] = []
    for markdown in ROOT.rglob("*.md"):
        if any(part in SKIP_PARTS for part in markdown.parts):
            continue
        for target in LINK_PATTERN.findall(markdown.read_text(encoding="utf-8")):
            target = target.strip().strip("<>")
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path: Path = (markdown.parent / unquote(target.split("#", 1)[0])).resolve()
            if not path.exists():
                errors.append(f"{markdown.relative_to(ROOT)}: missing {target}")
    return errors


def check_adr_index() -> list[str]:
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    expected = sorted((ROOT / "docs/adr").glob("ADR-*.md"))
    errors: list[str] = []
    for adr in expected:
        relative = adr.relative_to(ROOT / "docs").as_posix()
        if relative not in index:
            errors.append(f"docs/README.md: missing ADR {relative}")
    return errors


def check_sdk_version() -> list[str]:
    """The README's declared target SDK must match the sdk-check group pin."""
    groups = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "dependency-groups"
    ]
    pinned = next(
        (
            match.group(1)
            for spec in groups["sdk-check"]
            if (match := SDK_PIN_PATTERN.match(spec))
        ),
        None,
    )
    if pinned is None:
        return ["pyproject.toml: no openhands-sdk== pin in the sdk-check group"]
    declared = SDK_DECL_PATTERN.findall(
        (ROOT / "README.md").read_text(encoding="utf-8")
    )
    if not declared:
        return ["README.md: no 'OpenHands Software Agent SDK vX.Y.Z' declaration"]
    return [
        f"README.md: declares SDK v{version} but sdk-check pins {pinned}"
        for version in set(declared)
        if version != pinned
    ]


def main() -> int:
    errors = check_links() + check_adr_index() + check_sdk_version()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("documentation verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
