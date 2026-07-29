"""Import the data-only preload embedded in a GW2Skills editor page."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any

from gw2_wvw_data.builds.model import BuildRecord
from gw2_wvw_data.decoders.build_code import BuildCodeError, decode_build_code
from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.http import SafeHttpClient
from gw2_wvw_data.importers.js_literal import parse_js_literal


ARMOR_SLOTS = ("helm", "shoulders", "coat", "gloves", "leggings", "boots")
TRINKET_SLOTS = ("back", "amulet", "earring1", "earring2", "ring1", "ring2")
WEAPON_SLOTS = ("w11", "w12", "w21", "w22")

_ALLOWED_HOSTS = frozenset({"en.gw2skills.net"})
_EDITOR_MARKER = "new BuildEditor("
_SOURCE = "gw2skills"


def import_gw2skills(
    url: str,
    *,
    dataset: Mapping[str, Any],
    client: SafeHttpClient,
) -> BuildRecord:
    """Import a WvW Thief configuration without evaluating page JavaScript."""

    document = client.get_text(url, allowed_hosts=_ALLOWED_HOSTS)
    editor = _extract_editor_object(document.text)
    preload = editor.get("preload")
    if not isinstance(preload, Mapping):
        raise ImportError("GW2Skills BuildEditor preload is missing")
    if preload.get("mode") != "wvw":
        raise ImportError("GW2Skills build mode must be wvw")
    profession = preload.get("profession")
    if type(profession) is not int or profession != 6:
        raise ImportError("GW2Skills build profession must be Thief")

    chatlink = preload.get("chatlink")
    if not isinstance(chatlink, str) or not chatlink:
        raise ImportError("GW2Skills preload chatlink is missing")
    build_code = chatlink if chatlink.startswith(("&", "[")) else f"[&{chatlink}]"
    try:
        decoded = decode_build_code(build_code, dataset=dataset)
    except (BuildCodeError, ValueError) as error:
        raise ImportError("GW2Skills chatlink is invalid") from error

    equipment = preload.get("equipment")
    if not isinstance(equipment, Mapping):
        raise ImportError("GW2Skills equipment is missing")
    weapon_types = preload.get("weapon")
    if (
        not isinstance(weapon_types, list)
        or len(weapon_types) != len(WEAPON_SLOTS)
    ):
        raise ImportError("GW2Skills weapon slots are malformed")

    weapon_items, weapon_details, weapon_infusions = _read_slots(
        equipment, section="weapon", slots=WEAPON_SLOTS
    )
    armor, armor_details, armor_infusions = _read_slots(
        equipment, section="armor", slots=ARMOR_SLOTS
    )
    trinkets, trinket_details, trinket_infusions = _read_slots(
        equipment, section="trinket", slots=TRINKET_SLOTS
    )

    weapons = []
    for slot, weapon_type in zip(WEAPON_SLOTS, weapon_types, strict=True):
        type_ref = _site_component(_site_identifier(weapon_type, f"weapon.{slot}"))
        details = weapon_details.get(
            slot, {"quality": None, "upgrades": [], "infusions": []}
        )
        weapons.append(
            {
                "slot": slot,
                "type": type_ref,
                "item": weapon_items.get(slot),
                "quality": details["quality"],
                "upgrades": details["upgrades"],
                "infusions": details["infusions"],
            }
        )

    runes = []
    for slot in ARMOR_SLOTS:
        upgrades = armor_details.get(slot, {}).get("upgrades", [])
        if len(upgrades) > 1:
            raise ImportError(f"GW2Skills armor.{slot}.up has multiple values")
        runes.append(upgrades[0] if upgrades else None)

    buffs = equipment.get("buff", {})
    if not isinstance(buffs, Mapping):
        raise ImportError("GW2Skills equipment buff is malformed")
    food = _optional_component(buffs.get("food"), "buff.food")
    utility = _optional_component(buffs.get("utility"), "buff.utility")
    relic = _optional_component(equipment.get("relic"), "relic")

    source = {
        "source": _SOURCE,
        "url": url,
        "version": _optional_text(editor.get("version"), "version"),
        "balance": _optional_text(editor.get("balance"), "balance"),
    }
    fields = {
        "profession": {"source": _SOURCE},
        "mode": {"source": _SOURCE},
        "specializations": {"source": "build-code"},
        "traits": {"source": "build-code"},
        "skills": {"source": "build-code"},
        "weapons": {"source": _SOURCE},
        "armor": {"source": _SOURCE},
        "trinkets": {"source": _SOURCE},
        "runes": {"source": _SOURCE},
        "relic": {"source": _SOURCE},
        "infusions": {"source": _SOURCE},
        "consumables": {"source": _SOURCE},
    }
    identifier_payload = json.dumps(
        {"url": url, "preload": preload},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    decoded_value = decoded.to_dict()
    decoded_assumptions = decoded_value["assumptions"]
    decoded_provenance = decoded_value["provenance"]
    return BuildRecord.from_dict(
        {
            **decoded_value,
            "build_id": "gw2skills-" + hashlib.sha256(identifier_payload).hexdigest(),
            "weapons": weapons,
            "armor": armor,
            "trinkets": trinkets,
            "runes": runes,
            "relic": relic,
            "infusions": (
                weapon_infusions + armor_infusions + trinket_infusions
            ),
            "consumables": {"food": food, "utility": utility},
            "assumptions": {
                **decoded_assumptions,
                "gw2skills_equipment": {
                    "weapon": weapon_details,
                    "armor": armor_details,
                    "trinket": trinket_details,
                }
            },
            "provenance": {
                "sources": [*decoded_provenance["sources"], source],
                "fields": {
                    **decoded_provenance["fields"],
                    **fields,
                },
                "conflicts": decoded_provenance["conflicts"],
            },
            "version_audit": {
                "status": "unverifiable",
                "game_build_id": None,
                "checked_at": None,
                "affected_components": [],
                "warnings": [
                    "GW2Skills component IDs are site-local until explicitly mapped."
                ],
            },
        }
    )


def _extract_editor_object(html: str) -> Mapping[str, Any]:
    collector = _ScriptCollector()
    collector.feed(html)
    collector.close()
    calls = [
        (script, marker)
        for script in collector.scripts
        for marker in _script_markers(script)
    ]
    if not calls:
        raise ImportError("GW2Skills BuildEditor preload was not found")
    if len(calls) > 1:
        raise ImportError("GW2Skills page contains multiple BuildEditor calls")
    script, marker = calls[0]
    cursor = marker + len(_EDITOR_MARKER)
    while cursor < len(script) and script[cursor] in " \t\r\n\f\v":
        cursor += 1
    if cursor >= len(script) or script[cursor] != "{":
        raise ImportError("GW2Skills BuildEditor argument is not an object literal")

    end = _balanced_literal_end(script, cursor)
    after = end
    while after < len(script) and script[after] in " \t\r\n\f\v":
        after += 1
    if after >= len(script) or script[after] != ")":
        raise ImportError("GW2Skills BuildEditor call is malformed")
    value = parse_js_literal(script[cursor:end])
    if not isinstance(value, Mapping):
        raise ImportError("GW2Skills BuildEditor argument is malformed")
    return value


class _ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self._parts: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() == "script" and self._parts is None:
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._parts is not None:
            self.scripts.append("".join(self._parts))
            self._parts = None

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)


def _script_markers(script: str) -> list[int]:
    markers: list[int] = []
    cursor = 0
    while cursor < len(script):
        char = script[cursor]
        if char in "\"'`":
            cursor = _skip_script_string(script, cursor, char)
            continue
        if script.startswith("//", cursor):
            newline = script.find("\n", cursor + 2)
            cursor = len(script) if newline < 0 else newline + 1
            continue
        if script.startswith("/*", cursor):
            closing = script.find("*/", cursor + 2)
            cursor = len(script) if closing < 0 else closing + 2
            continue
        if script.startswith(_EDITOR_MARKER, cursor):
            markers.append(cursor)
            cursor += len(_EDITOR_MARKER)
            continue
        cursor += 1
    return markers


def _skip_script_string(script: str, cursor: int, quote: str) -> int:
    cursor += 1
    escaped = False
    while cursor < len(script):
        char = script[cursor]
        cursor += 1
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return cursor
    return cursor


def _balanced_literal_end(text: str, start: int) -> int:
    closing = {"{": "}", "[": "]", "(": ")"}
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    for cursor in range(start, len(text)):
        char = text[cursor]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char in closing:
            stack.append(closing[char])
            continue
        if char in "}])":
            if not stack or char != stack.pop():
                raise ImportError("GW2Skills BuildEditor delimiters are unbalanced")
            if not stack:
                return cursor + 1
    raise ImportError("GW2Skills BuildEditor object is unterminated")


def _read_slots(
    equipment: Mapping[str, Any],
    *,
    section: str,
    slots: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    section_value = equipment.get(section, {})
    if not isinstance(section_value, Mapping):
        raise ImportError(f"GW2Skills equipment {section} is malformed")
    items: dict[str, Any] = {}
    details: dict[str, Any] = {}
    infusions: list[Any] = []
    for slot in slots:
        if slot not in section_value:
            continue
        slot_value = section_value[slot]
        if not isinstance(slot_value, Mapping):
            raise ImportError(f"GW2Skills {section}.{slot} is malformed")
        item, quality = _item_component(
            slot_value.get("item"), f"{section}.{slot}.item"
        )
        upgrades = _tuple_components(
            slot_value.get("up"), f"{section}.{slot}.up"
        )
        slot_infusions = _tuple_components(
            slot_value.get("inf"), f"{section}.{slot}.inf"
        )
        items[slot] = item
        details[slot] = {
            "quality": quality,
            "upgrades": upgrades,
            "infusions": slot_infusions,
        }
        infusions.extend(slot_infusions)
    return items, details, infusions


def _item_component(value: Any, label: str) -> tuple[Any, int | None]:
    if value is None:
        return None, None
    if not isinstance(value, list) or len(value) != 2:
        raise ImportError(f"GW2Skills {label} is malformed")
    identifier = _site_identifier(value[0], label)
    quality = value[1] if len(value) > 1 else None
    if quality is not None and type(quality) is not int:
        raise ImportError(f"GW2Skills {label} quality is malformed")
    return _site_component(identifier), quality


def _tuple_components(value: Any, label: str) -> list[Any]:
    if value is None or value == []:
        return []
    tuples = (
        value
        if isinstance(value, list) and value and isinstance(value[0], list)
        else [value]
    )
    components = []
    for index, item in enumerate(tuples):
        if (
            not isinstance(item, list)
            or len(item) != 2
            or type(item[1]) is not int
        ):
            raise ImportError(f"GW2Skills {label} is malformed")
        identifier = _site_identifier(item[0], f"{label}[{index}]")
        components.append(_site_component(identifier))
    return components


def _optional_component(value: Any, label: str) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        if len(value) != 2 or any(type(item) is not int for item in value):
            raise ImportError(f"GW2Skills {label} is malformed")
        value = value[0]
    return _site_component(_site_identifier(value, label))


def _site_identifier(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ImportError(f"GW2Skills {label} identifier is malformed")
    return value


def _site_component(identifier: int) -> dict[str, Any] | None:
    if identifier == 0:
        return None
    return {
        "id": f"gw2skills:{identifier}",
        "name": None,
        "source": _SOURCE,
        "confidence": "publisher_claimed",
    }


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ImportError(f"GW2Skills {label} is malformed")
    return value
