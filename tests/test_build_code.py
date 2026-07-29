import base64
import json
from pathlib import Path

import pytest

from gw2_wvw_data.builds.model import ComponentRef
from gw2_wvw_data.decoders.build_code import BuildCodeError, decode_build_code


FIXTURE = Path(__file__).parent / "fixtures" / "builds" / "thief-template-codes.json"
CURRENT = Path(__file__).parents[1] / "data" / "normalized" / "current"
CODES = json.loads(FIXTURE.read_text("utf-8"))
VALID = CODES["valid"]


@pytest.fixture
def dataset():
    return {
        filename: json.loads((CURRENT / f"{filename}.json").read_text("utf-8"))
        for filename in ("profession", "specializations", "traits", "skills")
    }


def _code(payload):
    return "[&" + base64.b64encode(bytes(payload)).decode("ascii") + "]"


def _minimum_payload(*, profession=5):
    return bytearray([0x0D, profession, 54, 43, 44, 39, 7, 57] + [0] * 36)


def test_decodes_thief_header_specializations_traits_and_land_skills(dataset):
    build = decode_build_code(VALID, dataset=dataset)

    assert build.profession == "Thief"
    assert [(item.id, item.name) for item in build.specializations] == [
        (54, "Acrobatics"),
        (44, "Trickery"),
        (7, "Daredevil"),
    ]
    assert [(item.id, item.name) for item in build.traits] == [
        (1237, "Pain Response"),
        (1192, "Swindler's Equilibrium"),
        (1295, "Upper Hand"),
        (1163, "Thrill of the Crime"),
        (1277, "Bountiful Theft"),
        (1158, "Sleight of Hand"),
        (1933, "Marauder's Resilience"),
        (1893, "Havoc Specialist"),
        (2047, "Bounding Dodger"),
    ]
    assert build.skills["heal"] == ComponentRef(13021, "Withdraw", "build-code", "mapped")
    assert build.skills["utilities"] == (
        ComponentRef(13035, "Roll for Initiative", "build-code", "mapped"),
        ComponentRef(13002, "Shadowstep", "build-code", "mapped"),
        ComponentRef(13062, "Signet of Agility", "build-code", "mapped"),
    )
    assert build.skills["elite"] == ComponentRef(
        13085, "Dagger Storm", "build-code", "mapped"
    )
    assert build.assumptions["aquatic_skills"] == (None, None, None, None, None)
    assert build.armor == {}
    assert build.version_audit["status"] == "unverifiable"
    assert {value["source"] for value in build.provenance["fields"].values()} == {
        "build-code"
    }


def test_decodes_terrestrial_weapons_and_accepts_legacy_form(dataset):
    current = decode_build_code(VALID, dataset=dataset)
    legacy = decode_build_code(CODES["legacy_44_byte"], dataset=dataset)

    assert [
        (weapon["type"].id, weapon["type"].name)
        for weapon in current.weapons
    ] == [(5, "Axe"), (54, "Pistol"), (90, "Sword"), (47, "Dagger")]
    assert legacy.weapons == ()
    assert legacy.assumptions["skill_overrides"] == ()


def test_preserves_explicit_unselected_traits_and_unknown_nonzero_ids(dataset):
    payload = _minimum_payload()
    payload[2:8] = bytes([250, 0, 54, 1, 44, 0])
    payload[8:10] = (65535).to_bytes(2, "little")
    payload.extend([1])
    payload.extend((65535).to_bytes(2, "little"))
    payload.extend([1])
    payload.extend((999999).to_bytes(4, "little"))

    build = decode_build_code(_code(payload), dataset=dataset)

    assert build.specializations[0] == ComponentRef(
        250, None, "build-code", "unknown"
    )
    assert build.traits[:3] == (
        ComponentRef(None, None, "build-code", "unknown"),
        ComponentRef(None, None, "build-code", "unknown"),
        ComponentRef(None, None, "build-code", "unknown"),
    )
    assert build.skills["heal"] == ComponentRef(
        65535, None, "build-code", "unknown"
    )
    assert build.weapons[0]["type"] == ComponentRef(
        65535, None, "build-code", "unknown"
    )
    assert build.assumptions["skill_overrides"] == (
        ComponentRef(999999, None, "build-code", "unknown"),
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "empty"),
        ("not-prefixed", "prefix"),
        ("[&not-base64]", "base64"),
        ("[&" + "A" * 600 + "]", "512"),
        (" " * 513 + VALID, "512"),
        ("[&AgEAWgAA]", "build template header"),
    ],
)
def test_rejects_malformed_or_oversized_codes(value, message, dataset):
    with pytest.raises(BuildCodeError, match=message):
        decode_build_code(value, dataset=dataset)


def test_rejects_non_thief_template(dataset):
    with pytest.raises(
        BuildCodeError, match="only Thief build templates are supported"
    ):
        decode_build_code(_code(_minimum_payload(profession=7)), dataset=dataset)


def test_preserves_zero_weapon_as_explicit_unselected_value(dataset):
    payload = _minimum_payload()
    payload.extend([1, 0, 0, 0])

    build = decode_build_code(_code(payload), dataset=dataset)

    assert build.weapons[0]["type"] == ComponentRef(
        None, None, "build-code", "unknown"
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (_minimum_payload() + bytes([1]), "weapon"),
        (_minimum_payload() + bytes([0]), "skill override"),
        (_minimum_payload() + bytes([0, 1]), "skill override"),
        (_minimum_payload() + bytes([0, 0, 1]), "trailing"),
    ],
)
def test_rejects_truncated_dynamic_arrays_or_nonzero_trailing_bytes(
    payload, message, dataset
):
    with pytest.raises(BuildCodeError, match=message):
        decode_build_code(_code(payload), dataset=dataset)


def test_optional_brackets_normalize_to_the_same_deterministic_record(dataset):
    bracketed = decode_build_code(VALID, dataset=dataset)
    unbracketed = decode_build_code(VALID[1:-1], dataset=dataset)

    assert unbracketed == bracketed
    assert unbracketed.build_id == bracketed.build_id
