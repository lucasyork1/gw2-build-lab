from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def load_workflow(name: str) -> dict:
    with (WORKFLOWS / name).open(encoding="utf-8") as handle:
        return yaml.load(handle, Loader=yaml.BaseLoader)


def steps(workflow: dict) -> list[dict]:
    return [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]


def test_validate_workflow_uses_read_only_permissions_and_python_312():
    workflow = load_workflow("validate.yml")

    assert workflow["permissions"] == {"contents": "read"}
    assert "validate-data" in workflow["jobs"]
    assert {
        job["runs-on"] for job in workflow["jobs"].values()
    } == {"ubuntu-24.04"}
    assert any(
        step.get("uses") == "actions/setup-python@v6"
        and step.get("with", {}).get("python-version") == "3.12.11"
        for step in steps(workflow)
    )
    commands = "\n".join(step.get("run", "") for step in steps(workflow))
    assert "pytest" in commands
    assert "gw2-wvw-data validate" in commands
    assert "No current dataset" not in commands


def test_update_workflow_is_the_only_pr_writer_and_needs_no_api_key():
    update = load_workflow("check-update.yml")
    validate = load_workflow("validate.yml")
    release = load_workflow("release.yml")

    assert update["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert validate["permissions"] == {"contents": "read"}
    assert release["permissions"] == {"contents": "write"}
    source = (WORKFLOWS / "check-update.yml").read_text(encoding="utf-8").lower()
    assert "api_key" not in source
    assert "access_token" not in source
    assert "human review required" in source
    assert source.index("/v2/build") < source.index("gw2-wvw-data fetch")


def test_release_workflow_only_runs_for_data_version_tags():
    workflow = load_workflow("release.yml")

    assert workflow["on"] == {"push": {"tags": ["data-v*"]}}
    assert all(
        job["runs-on"] == "ubuntu-24.04"
        and
        any(
            step.get("uses") == "actions/setup-python@v6"
            and step.get("with", {}).get("python-version") == "3.12.11"
            for step in job.get("steps", [])
        )
        for job in workflow["jobs"].values()
    )
