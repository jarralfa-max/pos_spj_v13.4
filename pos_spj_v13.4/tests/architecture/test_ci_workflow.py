"""Protect executable CI and the validation gates on both sides of its merge."""

from pathlib import Path
import shlex

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci-segmented.yml"


@pytest.fixture
def workflow():
    # BaseLoader preserves the GitHub Actions `on` key as a string (YAML 1.2).
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _steps(workflow):
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def _pytest_targets(workflow):
    targets = set()
    for step in _steps(workflow):
        command = step.get("run", "").replace("\\\n", " ")
        for line in command.splitlines():
            tokens = shlex.split(line)
            if tokens[:3] == ["python", "-m", "pytest"]:
                targets.update(token for token in tokens[3:] if token.startswith("tests/"))
    return targets


def test_ci_workflow_is_valid_and_runs_on_push_and_pull_request(workflow):
    assert {"push", "pull_request"} <= workflow["on"].keys()
    assert workflow["jobs"]
    for job in workflow["jobs"].values():
        assert job["runs-on"]
        assert job["steps"]
        assert job.get("continue-on-error", "false") == "false"
        for step in job["steps"]:
            assert step.get("continue-on-error", "false") == "false"


def test_ci_preserves_full_architecture_unit_and_integration_gates(workflow):
    assert {"tests/architecture", "tests/unit", "tests/integration"} <= _pytest_targets(workflow)


def test_ci_explicitly_validates_security(workflow):
    assert {"tests/unit/security", "tests/integration/security"} <= _pytest_targets(workflow)


def test_ci_preserves_purchasing_visual_evidence_and_pwa_tests(workflow):
    assert "tests/ui/test_purchasing_visual_closure.py" in _pytest_targets(workflow)
    steps = _steps(workflow)
    assert any("node --test tests/pwa/*.test.mjs" in step.get("run", "") for step in steps)
    assert any("node --check" in step.get("run", "") for step in steps)
    uploads = [step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")]
    assert any(
        step.get("if") == "always()"
        and step["with"].get("path") == "visual-artifacts/"
        and step["with"].get("if-no-files-found") == "error"
        for step in uploads
    )


def test_ci_keeps_sales_ui_and_api_domain_jobs(workflow):
    assert {"ventas", "ui", "api"} <= workflow["jobs"].keys()
    for domain in ("ventas", "ui", "api"):
        assert any(
            f"scripts/ci/run_domain_tests.sh {domain}" in step.get("run", "")
            for step in workflow["jobs"][domain]["steps"]
        )
