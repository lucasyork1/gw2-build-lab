import json
from pathlib import Path

import httpx
import pytest

from gw2_wvw_data.builds import service
from gw2_wvw_data.cli import COMMAND_MODULES, main as cli_main
from gw2_wvw_data.importers.http import SafeHttpClient


ROOT = Path(__file__).parents[1]
CURRENT = ROOT / "data" / "normalized" / "current"
RULES = ROOT / "data" / "analysis-rules" / "thief-wvw-v1.json"
BUILD_FIXTURE = ROOT / "tests" / "fixtures" / "builds" / "minimal-thief.json"
CODE_FIXTURE = (
    ROOT / "tests" / "fixtures" / "builds" / "thief-template-codes.json"
)
GW2SKILLS_FIXTURE = (
    ROOT / "tests" / "fixtures" / "importers" / "gw2skills-thief.html"
)
METABATTLE_FIXTURE = (
    ROOT / "tests" / "fixtures" / "importers" / "metabattle-thief.html"
)
GW2SKILLS_URL = "https://en.gw2skills.net/editor/?fixture"
METABATTLE_URL = "https://metabattle.com/wiki/Build:Thief_-_Deadeye_Roamer"


def _client() -> SafeHttpClient:
    def respond(request: httpx.Request) -> httpx.Response:
        fixture = (
            METABATTLE_FIXTURE
            if request.url.host in {"metabattle.com", "www.metabattle.com"}
            else GW2SKILLS_FIXTURE
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=fixture.read_bytes(),
            request=request,
        )

    return SafeHttpClient(transport=httpx.MockTransport(respond))


def _analyze_arguments(tmp_path: Path) -> list[str]:
    code = json.loads(CODE_FIXTURE.read_text("utf-8"))["valid"]
    return [
        "analyze",
        "--build-code",
        code,
        "--dataset",
        str(CURRENT),
        "--rules",
        str(RULES),
        "--json",
        str(tmp_path / "analysis.json"),
        "--markdown",
        str(tmp_path / "analysis.md"),
    ]


def test_dispatcher_exposes_all_build_operations():
    assert COMMAND_MODULES["analyze"] == "builds.service"
    assert COMMAND_MODULES["import-source"] == "builds.service"
    assert COMMAND_MODULES["compare"] == "builds.service"


@pytest.mark.parametrize(
    "selection",
    [[], ["--build-code", "x", "--gw2skills-url", "y"]],
)
def test_analyze_requires_exactly_one_input_without_creating_outputs(
    tmp_path, selection
):
    json_output = tmp_path / "out.json"
    markdown_output = tmp_path / "out.md"
    arguments = [
        "analyze",
        *selection,
        "--dataset",
        str(CURRENT),
        "--json",
        str(json_output),
        "--markdown",
        str(markdown_output),
    ]

    with pytest.raises(SystemExit):
        service.main(arguments)

    assert not json_output.exists()
    assert not markdown_output.exists()


def test_invalid_analyze_input_does_not_create_either_output(tmp_path):
    json_output = tmp_path / "out.json"
    markdown_output = tmp_path / "out.md"

    with pytest.raises(ValueError, match="build template"):
        service.main(
            [
                "analyze",
                "--build-code",
                "not-a-build",
                "--dataset",
                str(CURRENT),
                "--rules",
                str(RULES),
                "--json",
                str(json_output),
                "--markdown",
                str(markdown_output),
            ]
        )

    assert not json_output.exists()
    assert not markdown_output.exists()


def test_dispatcher_analyze_writes_complete_byte_identical_bundle(tmp_path):
    arguments = _analyze_arguments(tmp_path)

    assert cli_main(arguments) == 0
    first_json = (tmp_path / "analysis.json").read_bytes()
    first_markdown = (tmp_path / "analysis.md").read_bytes()
    value = json.loads(first_json)
    assert set(value) == {"analysis", "audit", "build"}

    assert cli_main(arguments) == 0
    assert (tmp_path / "analysis.json").read_bytes() == first_json
    assert (tmp_path / "analysis.md").read_bytes() == first_markdown


def test_analyze_gw2skills_url_runs_offline_with_injected_client(tmp_path):
    json_output = tmp_path / "gw2skills.json"
    markdown_output = tmp_path / "gw2skills.md"

    result = service.main(
        [
            "analyze",
            "--gw2skills-url",
            GW2SKILLS_URL,
            "--dataset",
            str(CURRENT),
            "--rules",
            str(RULES),
            "--json",
            str(json_output),
            "--markdown",
            str(markdown_output),
        ],
        client=_client(),
    )

    assert result == 0
    assert json.loads(json_output.read_text("utf-8"))["build"]["build_id"].startswith(
        "gw2skills-"
    )
    assert markdown_output.read_text("utf-8").startswith(
        "# WvW Thief Build Analysis"
    )


def test_render_failure_leaves_both_analysis_outputs_absent(tmp_path, monkeypatch):
    arguments = _analyze_arguments(tmp_path)

    def fail_render(*args):
        raise RuntimeError("render failed")

    monkeypatch.setattr(service, "render_markdown", fail_render)
    with pytest.raises(RuntimeError, match="render failed"):
        service.main(arguments)

    assert not (tmp_path / "analysis.json").exists()
    assert not (tmp_path / "analysis.md").exists()


def test_import_source_writes_only_to_selected_candidate_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    candidate_dir = tmp_path / "selected-candidates"

    assert service.main(
        [
            "import-source",
            METABATTLE_URL,
            "--dataset",
            str(CURRENT),
            "--candidate-dir",
            str(candidate_dir),
        ],
        client=_client(),
    ) == 0

    candidates = list(candidate_dir.glob("*.json"))
    assert len(candidates) == 1
    value = json.loads(candidates[0].read_text("utf-8"))
    assert value["source_name"] == "MetaBattle"
    assert value["build"] is not None
    assert not (tmp_path / "data" / "community-builds").exists()


def test_compare_writes_byte_identical_json_and_markdown(tmp_path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_bytes(BUILD_FIXTURE.read_bytes())
    right_value = json.loads(BUILD_FIXTURE.read_text("utf-8"))
    right_value["build_id"] = "fixture-right"
    right.write_text(json.dumps(right_value), encoding="utf-8")
    arguments = [
        "compare",
        str(left),
        str(right),
        "--json",
        str(tmp_path / "comparison.json"),
        "--markdown",
        str(tmp_path / "comparison.md"),
    ]

    assert service.main(arguments) == 0
    first_json = (tmp_path / "comparison.json").read_bytes()
    first_markdown = (tmp_path / "comparison.md").read_bytes()
    assert json.loads(first_json)["left_build_id"] == "fixture-minimal-thief"

    assert service.main(arguments) == 0
    assert (tmp_path / "comparison.json").read_bytes() == first_json
    assert (tmp_path / "comparison.md").read_bytes() == first_markdown
