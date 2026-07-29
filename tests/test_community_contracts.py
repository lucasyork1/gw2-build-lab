from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"


def template_fields(name: str) -> set[str]:
    payload = yaml.load(
        (TEMPLATES / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    return {
        item["id"]
        for item in payload["body"]
        if item.get("id")
    }


def test_issue_forms_capture_version_source_and_testing_context():
    expected = {
        "game_build",
        "effective_patch",
        "source_url",
        "build_code",
        "wvw_context",
        "testing_notes",
        "conflict_of_interest",
    }

    for name in ("stale-build.yml", "data-error.yml", "new-build.yml"):
        assert expected <= template_fields(name)


def test_contribution_rules_prohibit_secrets_and_copied_guides():
    contribution_rules = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").lower()

    assert "api key" in contribution_rules
    assert "do not submit" in contribution_rules
    assert "third-party guide text" in contribution_rules
    assert "third-party images" in contribution_rules
    assert "structural validity" in contribution_rules
    assert "combat effectiveness" in contribution_rules


def test_code_and_data_licenses_are_separate():
    code_license = (ROOT / "LICENSE").read_text(encoding="utf-8")
    data_license = (ROOT / "DATA-LICENSE.md").read_text(encoding="utf-8")

    assert "MIT License" in code_license
    assert "Creative Commons Attribution 4.0" in data_license
    assert "ArenaNet" in data_license
    assert "excluded" in data_license.lower()
