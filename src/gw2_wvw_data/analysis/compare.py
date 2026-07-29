"""Combat-claim-free structural comparison of canonical builds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from gw2_wvw_data.builds.model import BuildRecord, ComponentRef


_CATEGORY_ORDER = (
    "specializations",
    "traits",
    "skills",
    "weapons",
    "armor",
    "trinkets",
    "runes",
    "relic",
    "infusions",
    "consumables",
)
_ARMOR_SLOTS = ("helm", "shoulders", "coat", "gloves", "leggings", "boots")
_TRINKET_SLOTS = (
    "back",
    "amulet",
    "earring1",
    "earring2",
    "ring1",
    "ring2",
)


@dataclass(frozen=True)
class StructuralChange:
    category: str
    path: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "path": self.path,
            "value": _public_value(self.value),
        }


@dataclass(frozen=True)
class StructuralReplacement:
    category: str
    path: str
    before: Any
    after: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "path": self.path,
            "before": _public_value(self.before),
            "after": _public_value(self.after),
        }


@dataclass(frozen=True)
class BuildComparison:
    left_build_id: str
    right_build_id: str
    additions: tuple[StructuralChange, ...]
    removals: tuple[StructuralChange, ...]
    replacements: tuple[StructuralReplacement, ...]

    @property
    def changes(
        self,
    ) -> tuple[StructuralChange | StructuralReplacement, ...]:
        return (*self.additions, *self.removals, *self.replacements)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_build_id": self.left_build_id,
            "right_build_id": self.right_build_id,
            "additions": [item.to_dict() for item in self.additions],
            "removals": [item.to_dict() for item in self.removals],
            "replacements": [
                item.to_dict() for item in self.replacements
            ],
        }


def compare_builds(
    left: BuildRecord, right: BuildRecord
) -> BuildComparison:
    """Report only ordered canonical structure changes."""

    left_fields = dict(_comparison_fields(left))
    right_fields = dict(_comparison_fields(right))
    ordered_paths = list(
        dict.fromkeys([*left_fields.keys(), *right_fields.keys()])
    )
    order = {path: position for position, path in enumerate(ordered_paths)}
    additions: list[StructuralChange] = []
    removals: list[StructuralChange] = []
    replacements: list[StructuralReplacement] = []
    for path in ordered_paths:
        left_value = left_fields.get(path)
        right_value = right_fields.get(path)
        if left_value is None and right_value is None:
            continue
        if path not in left_fields or (
            left_value is None and right_value is not None
        ):
            additions.append(
                StructuralChange(_category(path), path, right_value)
            )
        elif path not in right_fields or (
            left_value is not None and right_value is None
        ):
            removals.append(
                StructuralChange(_category(path), path, left_value)
            )
        elif _identity(left_value) != _identity(right_value):
            replacements.append(
                StructuralReplacement(
                    _category(path), path, left_value, right_value
                )
            )
    key = lambda item: (
        _CATEGORY_ORDER.index(item.category),
        order[item.path],
    )
    additions.sort(key=key)
    removals.sort(key=key)
    replacements.sort(key=key)
    return BuildComparison(
        left_build_id=left.build_id,
        right_build_id=right.build_id,
        additions=tuple(additions),
        removals=tuple(removals),
        replacements=tuple(replacements),
    )


def _comparison_fields(build: BuildRecord) -> Iterable[tuple[str, Any]]:
    for position, item in enumerate(build.specializations):
        yield f"specializations[{position}]", item
    for position, item in enumerate(build.traits):
        yield f"traits[{position}]", item
    yield "skills.heal", build.skills.get("heal")
    utilities = build.skills.get("utilities", ())
    if isinstance(utilities, tuple):
        for position, item in enumerate(utilities):
            yield f"skills.utilities[{position}]", item
    yield "skills.elite", build.skills.get("elite")

    yield from _weapon_fields(build.weapons)

    yield from _slot_fields("armor", build.armor, _ARMOR_SLOTS)
    yield from _slot_fields("trinkets", build.trinkets, _TRINKET_SLOTS)
    for position, item in enumerate(build.runes):
        yield f"runes[{position}]", item
    yield "relic", build.relic
    for position, item in enumerate(build.infusions):
        yield f"infusions[{position}]", item
    for slot in ("food", "utility"):
        yield f"consumables.{slot}", build.consumables.get(slot)


def _slot_fields(
    category: str,
    values: Mapping[str, Any],
    standard_slots: tuple[str, ...],
) -> Iterable[tuple[str, Any]]:
    for slot in (
        *standard_slots,
        *sorted(set(values) - set(standard_slots)),
    ):
        if slot in values:
            yield f"{category}.{slot}", values[slot]


def _weapon_fields(
    weapons: tuple[Mapping[str, Any], ...],
) -> Iterable[tuple[str, Any]]:
    occurrences: dict[str, int] = {}
    unkeyed = 0
    for weapon in weapons:
        slot = weapon.get("slot")
        if isinstance(slot, str):
            occurrence = occurrences.get(slot, 0)
            occurrences[slot] = occurrence + 1
            suffix = "" if occurrence == 0 else f"[{occurrence}]"
            prefix = f"weapons.{slot}{suffix}"
            slot_value = slot
        else:
            prefix = f"weapons.unkeyed[{unkeyed}]"
            unkeyed += 1
            slot_value = "<missing>"
        yield f"{prefix}.slot", slot_value
        for field in ("quality", "type", "item"):
            if field in weapon:
                yield f"{prefix}.{field}", weapon[field]
        for group in ("upgrades", "infusions"):
            values = weapon.get(group, ())
            if isinstance(values, tuple):
                for position, item in enumerate(values):
                    yield f"{prefix}.{group}[{position}]", item


def _category(path: str) -> str:
    return path.split(".", 1)[0].split("[", 1)[0]


def _identity(value: Any) -> Any:
    if isinstance(value, ComponentRef):
        return ("component", value.id)
    if isinstance(value, Mapping):
        return tuple(
            (key, _identity(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, tuple):
        return tuple(_identity(item) for item in value)
    return value


def _public_value(value: Any) -> Any:
    if isinstance(value, ComponentRef):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {
            key: _public_value(item) for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_public_value(item) for item in value]
    return value
