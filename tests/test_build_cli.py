import json
from dataclasses import replace
from importlib.resources import files
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


def test_packaged_default_rules_match_the_public_rules():
    packaged = (
        files("gw2_wvw_data")
        .joinpath("data")
        .joinpath("analysis-rules")
        .joinpath("thief-wvw-v1.json")
    )

    assert packaged.read_bytes() == RULES.read_bytes()


def test_default_rules_work_outside_the_repository(tmp_path, monkeypatch):
    arguments = _analyze_arguments(tmp_path)
    rules_position = arguments.index("--rules")
    del arguments[rules_position : rules_position + 2]
    monkeypatch.chdir(tmp_path)

    assert cli_main(arguments) == 0
    assert (tmp_path / "analysis.json").is_file()
    assert (tmp_path / "analysis.md").is_file()


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


@pytest.mark.parametrize(
    "checked_at",
    [
        "2026-07-29",
        "2026-07-29T02:05:07",
        "2026-07-29T02:05:07Z trailing",
        "2026-07-29T02:05:07+05",
    ],
)
def test_checked_at_rejects_incomplete_or_naive_datetimes(checked_at):
    with pytest.raises(ValueError, match="timezone-aware RFC 3339"):
        service._checked_at({"manifest": {"fetched_at": checked_at}})


@pytest.mark.parametrize(
    "checked_at",
    [
        "2026-07-29T02:05:07Z",
        "2026-07-29T02:05:07.123456-05:00",
    ],
)
def test_checked_at_accepts_complete_timezone_aware_rfc3339(checked_at):
    assert (
        service._checked_at({"manifest": {"fetched_at": checked_at}})
        == checked_at
    )


def test_malformed_manifest_timestamp_leaves_both_outputs_absent(
    tmp_path, monkeypatch
):
    dataset = service.load_dataset(CURRENT)
    dataset["manifest"] = {
        **dataset["manifest"],
        "fetched_at": "2026-07-29",
    }
    monkeypatch.setattr(service, "load_dataset", lambda path: dataset)
    arguments = _analyze_arguments(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware RFC 3339"):
        service.main(arguments)

    assert not (tmp_path / "analysis.json").exists()
    assert not (tmp_path / "analysis.md").exists()


def test_invalid_audit_contract_leaves_both_outputs_absent(
    tmp_path, monkeypatch
):
    real_audit_build = service.audit_build

    def invalid_audit(*args, **kwargs):
        return replace(
            real_audit_build(*args, **kwargs),
            status="not-a-public-status",
        )

    monkeypatch.setattr(service, "audit_build", invalid_audit)

    with pytest.raises(ValueError, match="build audit schema invalid"):
        service.main(_analyze_arguments(tmp_path))

    assert not (tmp_path / "analysis.json").exists()
    assert not (tmp_path / "analysis.md").exists()


def test_invalid_analysis_contract_leaves_both_outputs_absent(
    tmp_path, monkeypatch
):
    real_analyze_build = service.analyze_build

    def invalid_analysis(*args, **kwargs):
        return replace(
            real_analyze_build(*args, **kwargs),
            ruleset_id="",
        )

    monkeypatch.setattr(service, "analyze_build", invalid_analysis)

    with pytest.raises(ValueError, match="build analysis schema invalid"):
        service.main(_analyze_arguments(tmp_path))

    assert not (tmp_path / "analysis.json").exists()
    assert not (tmp_path / "analysis.md").exists()


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


@pytest.mark.parametrize("prior_outputs", [None, (b"old-json", b"old-markdown")])
def test_output_pair_rolls_back_when_second_final_replace_fails(
    tmp_path, monkeypatch, prior_outputs
):
    json_output = tmp_path / "analysis.json"
    markdown_output = tmp_path / "analysis.md"
    if prior_outputs is not None:
        json_output.write_bytes(prior_outputs[0])
        markdown_output.write_bytes(prior_outputs[1])
    path_type = type(json_output)
    original_replace = path_type.replace
    injected = False

    def fail_second_final_replace(path, target):
        nonlocal injected
        if (
            not injected
            and Path(target) == markdown_output
            and ".backup." not in path.name
        ):
            injected = True
            raise OSError("injected second replace failure")
        return original_replace(path, target)

    monkeypatch.setattr(path_type, "replace", fail_second_final_replace)

    with pytest.raises(OSError, match="injected second replace failure"):
        service._write_output_pair(
            json_output,
            b"new-json",
            markdown_output,
            b"new-markdown",
        )

    if prior_outputs is None:
        assert not json_output.exists()
        assert not markdown_output.exists()
        assert list(tmp_path.iterdir()) == []
    else:
        assert json_output.read_bytes() == prior_outputs[0]
        assert markdown_output.read_bytes() == prior_outputs[1]
        assert sorted(tmp_path.iterdir()) == sorted(
            (json_output, markdown_output)
        )


def test_output_pair_cleans_first_backup_when_second_backup_creation_fails(
    tmp_path, monkeypatch
):
    json_output = tmp_path / "analysis.json"
    markdown_output = tmp_path / "analysis.md"
    json_output.write_bytes(b"old-json")
    markdown_output.write_bytes(b"old-markdown")
    real_backup_destination = service._backup_destination
    calls = 0

    def fail_second_backup(destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second backup failure")
        return real_backup_destination(destination)

    monkeypatch.setattr(
        service,
        "_backup_destination",
        fail_second_backup,
    )

    with pytest.raises(OSError, match="injected second backup failure"):
        service._write_output_pair(
            json_output,
            b"new-json",
            markdown_output,
            b"new-markdown",
        )

    assert json_output.read_bytes() == b"old-json"
    assert markdown_output.read_bytes() == b"old-markdown"
    assert sorted(tmp_path.iterdir()) == sorted(
        (json_output, markdown_output)
    )


def test_output_pair_retains_recovery_backup_when_backup_restore_fails(
    tmp_path, monkeypatch
):
    json_output = tmp_path / "analysis.json"
    markdown_output = tmp_path / "analysis.md"
    json_output.write_bytes(b"old-json")
    markdown_output.write_bytes(b"old-markdown")
    path_type = type(json_output)
    original_replace = path_type.replace
    final_failure_injected = False
    restore_failure_injected = False

    def fail_final_and_json_restore(path, target):
        nonlocal final_failure_injected, restore_failure_injected
        target = Path(target)
        if (
            not final_failure_injected
            and target == markdown_output
            and ".backup." not in path.name
        ):
            final_failure_injected = True
            raise OSError("injected second final replace failure")
        if (
            not restore_failure_injected
            and target == json_output
            and ".backup." in path.name
        ):
            restore_failure_injected = True
            raise OSError("injected JSON backup restore failure")
        return original_replace(path, target)

    monkeypatch.setattr(
        path_type,
        "replace",
        fail_final_and_json_restore,
    )

    with pytest.raises(
        RuntimeError,
        match="rollback was incomplete",
    ) as caught:
        service._write_output_pair(
            json_output,
            b"new-json",
            markdown_output,
            b"new-markdown",
        )

    recovery_backups = list(
        tmp_path.glob(".analysis.json.backup.*.tmp")
    )
    assert len(recovery_backups) == 1
    assert recovery_backups[0].read_bytes() == b"old-json"
    assert str(recovery_backups[0]) in str(caught.value)
    assert json_output.read_bytes() == b"new-json"
    assert markdown_output.read_bytes() == b"old-markdown"
    assert sorted(tmp_path.iterdir()) == sorted(
        (json_output, markdown_output, recovery_backups[0])
    )


def test_output_pair_preflights_directory_destination_before_replacement(
    tmp_path,
):
    json_output = tmp_path / "analysis.json"
    markdown_output = tmp_path / "analysis.md"
    json_output.write_bytes(b"old-json")
    markdown_output.mkdir()

    with pytest.raises(ValueError, match="output destination is a directory"):
        service._write_output_pair(
            json_output,
            b"new-json",
            markdown_output,
            b"new-markdown",
        )

    assert json_output.read_bytes() == b"old-json"
    assert markdown_output.is_dir()
    assert list(markdown_output.iterdir()) == []


def test_output_pair_rejects_colliding_destinations(tmp_path):
    output = tmp_path / "analysis.out"

    with pytest.raises(ValueError, match="different paths"):
        service._write_output_pair(output, b"json", output, b"markdown")

    assert not output.exists()


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
