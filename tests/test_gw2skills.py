import json
from pathlib import Path

import httpx
import pytest

from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.gw2skills import import_gw2skills
from gw2_wvw_data.importers.http import SafeHttpClient


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "importers"
    / "gw2skills-thief.html"
)
CURRENT = Path(__file__).parents[1] / "data" / "normalized" / "current"
URL = "https://en.gw2skills.net/editor/?fixture"


@pytest.fixture
def dataset():
    return {
        filename: json.loads((CURRENT / f"{filename}.json").read_text("utf-8"))
        for filename in ("profession", "specializations", "traits", "skills")
    }


def _client(html):
    return SafeHttpClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=html.encode("utf-8"),
                request=request,
            )
        )
    )


def _ids(values):
    return [value.id if value is not None else None for value in values]


def test_imports_chatlink_and_all_explicit_equipment_slots(dataset):
    build = import_gw2skills(
        URL,
        dataset=dataset,
        client=_client(FIXTURE.read_text("utf-8")),
    )

    assert [value.id for value in build.specializations] == [54, 44, 7]
    assert [value.id for value in build.traits] == [
        1237,
        1192,
        1703,
        1163,
        1277,
        1158,
        2023,
        1893,
        1964,
    ]
    assert build.skills["heal"].id == 13021
    assert _ids(build.skills["utilities"]) == [13035, 13062, 13002]
    assert build.skills["elite"].id == 13085

    assert list(build.armor) == [
        "helm",
        "shoulders",
        "coat",
        "gloves",
        "leggings",
        "boots",
    ]
    assert _ids(build.armor.values()) == [
        "gw2skills:300",
        "gw2skills:301",
        "gw2skills:302",
        "gw2skills:303",
        "gw2skills:304",
        "gw2skills:305",
    ]
    assert list(build.trinkets) == [
        "back",
        "amulet",
        "earring1",
        "earring2",
        "ring1",
        "ring2",
    ]
    assert _ids(build.trinkets.values()) == [
        "gw2skills:310",
        "gw2skills:311",
        "gw2skills:312",
        "gw2skills:313",
        "gw2skills:314",
        "gw2skills:315",
    ]
    assert [
        (weapon["slot"], weapon["type"].id, weapon["item"].id)
        for weapon in build.weapons
    ] == [
        ("w11", "gw2skills:13", "gw2skills:290"),
        ("w12", "gw2skills:9", "gw2skills:291"),
        ("w21", "gw2skills:9", "gw2skills:292"),
        ("w22", "gw2skills:11", "gw2skills:293"),
    ]
    assert _ids(build.runes) == [
        "gw2skills:201",
        "gw2skills:202",
        "gw2skills:203",
        "gw2skills:204",
        "gw2skills:205",
        "gw2skills:206",
    ]
    assert build.relic.id == "gw2skills:323"
    assert build.consumables["food"].id == "gw2skills:544"
    assert build.consumables["utility"].id == "gw2skills:38"
    assert _ids(build.infusions) == [
        "gw2skills:901",
        "gw2skills:902",
        "gw2skills:903",
        "gw2skills:904",
        "gw2skills:910",
        "gw2skills:911",
        "gw2skills:912",
        "gw2skills:913",
        "gw2skills:914",
        "gw2skills:915",
        "gw2skills:920",
        "gw2skills:921",
        "gw2skills:922",
        "gw2skills:923",
        "gw2skills:924",
        "gw2skills:925",
    ]

    details = build.assumptions["gw2skills_equipment"]["weapon"]["w11"]
    assert details["quality"] == 6
    assert _ids(details["upgrades"]) == ["gw2skills:121", "gw2skills:122"]
    assert _ids(details["infusions"]) == ["gw2skills:901"]
    assert build.version_audit["status"] == "unverifiable"


def test_records_raw_editor_url_and_site_revision(dataset):
    build = import_gw2skills(
        URL,
        dataset=dataset,
        client=_client(FIXTURE.read_text("utf-8")),
    )

    assert build.provenance["sources"] == (
        {
            "source": "build-code",
            "value": (
                "[&DQU2OywnByoKAQAAGQEAAFcBAABYAAAAnwE"
                "AAAAAAAAAAAAAAAAAAAAAAAA=]"
            ),
        },
        {
            "source": "gw2skills",
            "url": URL,
            "version": "9.1.4",
            "balance": "2026/06/02 rev. 1",
        },
    )
    assert build.provenance["fields"]["armor"]["source"] == "gw2skills"
    assert build.provenance["fields"]["traits"]["source"] == "build-code"
    assert (
        build.provenance["fields"]["assumptions.profession_specific"][
            "source"
        ]
        == "build-code"
    )
    assert build.assumptions["aquatic_skills"] == (None,) * 5
    assert build.assumptions["profession_specific"] == (0,) * 16
    assert build.assumptions["skill_overrides"] == ()
    assert "gw2skills_equipment" in build.assumptions


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('mode: "wvw"', 'mode: "pve"', "mode"),
        ("profession: 6", "profession: 7", "profession"),
    ],
)
def test_rejects_non_wvw_or_non_thief_preload(old, new, message, dataset):
    html = FIXTURE.read_text("utf-8").replace(old, new)

    with pytest.raises(ImportError, match=message):
        import_gw2skills(URL, dataset=dataset, client=_client(html))


def test_rejects_missing_or_malformed_build_editor_preload(dataset):
    for html in (
        "<html><script>const value = {};</script></html>",
        "<script>new BuildEditor({preload: {mode: 'wvw'}};</script>",
        "<script>new BuildEditor({preload: fn()});</script>",
    ):
        with pytest.raises(ImportError):
            import_gw2skills(URL, dataset=dataset, client=_client(html))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("item: [290,6]", "item: [290,6,999]", "item"),
        ("up: [123,6]", 'up: [123,"bad"]', "up"),
        ("inf: [902,6]", "inf: [902]", "inf"),
    ],
)
def test_rejects_malformed_equipment_component_tuple(
    old, new, message, dataset
):
    html = FIXTURE.read_text("utf-8").replace(old, new)

    with pytest.raises(ImportError, match=message):
        import_gw2skills(URL, dataset=dataset, client=_client(html))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('"food": 544', '"food": [544,6,999]', "buff.food"),
        ("relic: 323", 'relic: [323,"bad"]', "relic"),
    ],
)
def test_rejects_malformed_buff_or_relic_tuple(old, new, message, dataset):
    html = FIXTURE.read_text("utf-8").replace(old, new)

    with pytest.raises(ImportError, match=message):
        import_gw2skills(URL, dataset=dataset, client=_client(html))


def test_accepts_exact_buff_and_relic_component_tuples(dataset):
    html = (
        FIXTURE.read_text("utf-8")
        .replace('"food": 544', '"food": [544,6]')
        .replace("relic: 323", "relic: [323,6]")
    )

    build = import_gw2skills(URL, dataset=dataset, client=_client(html))

    assert build.consumables["food"].id == "gw2skills:544"
    assert build.relic.id == "gw2skills:323"


@pytest.mark.parametrize(
    "script",
    [
        'const sample = "new BuildEditor({preload: {}})";',
        "// new BuildEditor({preload: {}})\nconst sample = 1;",
        "/* new BuildEditor({preload: {}}) */ const sample = 1;",
    ],
)
def test_ignores_build_editor_markers_inside_script_strings_or_comments(
    script, dataset
):
    html = f"<html><script>{script}</script></html>"

    with pytest.raises(ImportError, match="not found"):
        import_gw2skills(URL, dataset=dataset, client=_client(html))


def test_ignores_string_marker_when_real_build_editor_call_exists(dataset):
    html = FIXTURE.read_text("utf-8").replace(
        "E = new BuildEditor(",
        'const sample = "new BuildEditor({preload: {}})";\n'
        "E = new BuildEditor(",
    )

    build = import_gw2skills(URL, dataset=dataset, client=_client(html))

    assert build.profession == "Thief"


def test_preserves_explicit_missing_equipment_slots(dataset):
    html = (
        FIXTURE.read_text("utf-8")
        .replace(
            "        w12: {item: [291,6], up: [123,6], inf: [902,6]},\n",
            "",
        )
        .replace(
            "        helm: {item: [300,6], up: [201,6], inf: [910,6]},\n",
            "",
        )
    )

    build = import_gw2skills(URL, dataset=dataset, client=_client(html))

    assert build.weapons[1]["slot"] == "w12"
    assert build.weapons[1]["item"] is None
    assert "helm" not in build.armor
    assert build.runes[0] is None
