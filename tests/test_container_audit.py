"""Replay embedded workflow Python against captured trivy fixtures.

The container-audit aggregation and the publish gate-failure summary live
inside heredocs in the workflows; these tests extract the exact script
bodies and run them against fixtures shaped like the real scanner output
(the CIS fixture mirrors the DS-0002/DS-0026 failures the pinned image
reports), so a workflow edit that breaks the report JSON or the issue
body fails here instead of on the weekly run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CONTAINER_AUDIT = REPO_ROOT / ".github/workflows/container-audit.yml"
PUBLISH = REPO_ROOT / ".github/workflows/publish-bard-images.yml"


def _workflow_python(workflow: Path, marker: str) -> str:
    """Return the dedented body of the first ``<<'PY'`` heredoc that
    appears after ``marker`` in the workflow file."""
    text = workflow.read_text(encoding="utf-8")
    start = text.index(marker)
    heredoc = text.index("<<'PY'", start)
    body_start = text.index("\n", heredoc) + 1
    end = re.search(r"\n[ ]*PY\n", text[body_start:])
    assert end is not None, f"no PY terminator after {marker} in {workflow}"
    return textwrap.dedent(text[body_start : body_start + end.start()])


def _run_python(
    body: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, "-c", body],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=merged,
    )


def _compute_env(tmp_path: Path) -> dict[str, str]:
    (tmp_path / "lynis-out").mkdir()
    (tmp_path / "lynis-out" / "lynis-report.dat").write_text(
        "hardening_index=72\nwarning[]=test-warning\n", encoding="utf-8"
    )
    (tmp_path / "trivy-cis.json").write_bytes(
        (FIXTURES / "trivy-cis.json").read_bytes()
    )
    (tmp_path / "trivy-image.json").write_bytes(
        (FIXTURES / "trivy-image.json").read_bytes()
    )
    return {
        "LYNIS_OUT": str(tmp_path / "lynis-out"),
        "TRIVY_JSON": str(tmp_path / "trivy-image.json"),
        "TRIVY_CIS": str(tmp_path / "trivy-cis.json"),
        "REPORT_JSON": str(tmp_path / "container-hardening.json"),
        "PINNED_IMAGE": "ghcr.io/vibebb/bard-tools@sha256:" + "0" * 64,
    }


def test_cis_aggregation_extracts_failures(tmp_path: Path) -> None:
    body = _workflow_python(CONTAINER_AUDIT, "Compute container-hardening report")
    env = _compute_env(tmp_path)
    result = _run_python(body, env, tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(Path(env["REPORT_JSON"]).read_text(encoding="utf-8"))
    assert report["cis_docker"]["passed"] == 4
    assert report["cis_docker"]["failed"] == 2
    failures = report["cis_docker"]["failures"]
    assert [f["id"] for f in failures] == ["DS-0002", "DS-0026"]
    assert failures[0]["severity"] == "HIGH"
    assert "root" in failures[0]["title"]
    trivy = report["trivy"]
    assert trivy["fixable_high_or_critical"] == 2
    assert trivy["secrets"] == 1
    assert trivy["license_findings"] == 1
    # CRITICAL first in the fixable list
    assert [v["id"] for v in trivy["top_fixable"]] == ["CVE-2026-0001", "CVE-2026-0002"]
    assert trivy["top_fixable"][0]["fixed"] == "3.0.17-1"
    assert report["gate"]["fixable_high_or_critical"] == 2


def test_cis_empty_results_still_fail_closed(tmp_path: Path) -> None:
    body = _workflow_python(CONTAINER_AUDIT, "Compute container-hardening report")
    env = _compute_env(tmp_path)
    (tmp_path / "trivy-cis.json").write_text('{"Results": []}', encoding="utf-8")
    result = _run_python(body, env, tmp_path)
    assert result.returncode != 0
    assert "Docker CIS scan produced no results" in result.stderr


def test_report_markdown_lists_failed_checks_and_fixable_cves(tmp_path: Path) -> None:
    compute = _workflow_python(CONTAINER_AUDIT, "Compute container-hardening report")
    env = _compute_env(tmp_path)
    assert _run_python(compute, env, tmp_path).returncode == 0
    render = _workflow_python(CONTAINER_AUDIT, "<<'PY' > \"$REPORT_MD\"")
    md = _run_python(
        render,
        {
            "REPORT_JSON": env["REPORT_JSON"],
            "PREV_MD": str(tmp_path / "prev.md"),
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "VibeBB/bard-agent",
            "GITHUB_RUN_ID": "1",
        },
        tmp_path,
    )
    assert md.returncode == 0, md.stderr
    out = md.stdout
    assert "### Failed CIS Docker checks" in out
    assert "| DS-0002 | HIGH |" in out
    assert "| DS-0026 | LOW |" in out
    assert "### Top fixable vulnerabilities" in out
    assert "| CVE-2026-0001 | libssl3 | CRITICAL | 3.0.17-1 |" in out
    assert "| CVE-2026-0002 | bash | HIGH | 5.2.15-2 |" in out


def test_publish_gate_summary_renders_offending_rules(tmp_path: Path) -> None:
    body = _workflow_python(PUBLISH, "Summarize Trivy gate failure")
    (tmp_path / "trivy-image.sarif").write_bytes(
        (FIXTURES / "trivy-image.sarif").read_bytes()
    )
    result = _run_python(body, {}, tmp_path)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "### Trivy gate: fixable CRITICAL/HIGH findings" in out
    assert "| CVE-2026-0001 | 9.8 | error |" in out
    assert "| CVE-2026-0002 | 7.5 | error |" in out


def test_publish_gate_summary_empty_results(tmp_path: Path) -> None:
    body = _workflow_python(PUBLISH, "Summarize Trivy gate failure")
    (tmp_path / "trivy-image.sarif").write_text(
        '{"runs": [{"results": []}]}', encoding="utf-8"
    )
    result = _run_python(body, {}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Trivy gate" not in result.stdout
