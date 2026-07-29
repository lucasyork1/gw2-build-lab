"""Completeness, legality, resolution, and freshness checks for builds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from gw2_wvw_data.audit.index import DatasetIndex
from gw2_wvw_data.audit.version import AffectedComponent, PatchEvent
from gw2_wvw_data.builds.model import BuildRecord, ComponentRef


_ARMOR_SLOTS = ("helm", "shoulders", "coat", "gloves", "leggings", "boots")
_TRINKET_SLOTS = (
    "back",
    "amulet",
    "earring1",
    "earring2",
    "ring1",
    "ring2",
)
_WEAPON_SLOTS = ("w11", "w12", "w21", "w22")
_ISO_TIMEZONE_SUFFIX = re.compile(
    r"(?:Z|[+-](?:[01]\d|2[0-3])(?::?[0-5]\d)?)\Z"
)
_ARMOR_TYPES = {
    "helm": "Helm",
    "shoulders": "Shoulders",
    "coat": "Coat",
    "gloves": "Gloves",
    "leggings": "Leggings",
    "boots": "Boots",
}
_TRINKET_TYPES = {
    "amulet": "Amulet",
    "earring1": "Accessory",
    "earring2": "Accessory",
    "ring1": "Ring",
    "ring2": "Ring",
}
_WEAPON_TYPE_NORMALIZATION = {
    "LongBow": "Longbow",
    "ShortBow": "Shortbow",
}
_TWO_HANDED_WEAPONS = frozenset(
    {"Rifle", "Shortbow", "Staff", "Spear", "Speargun"}
)


@dataclass(frozen=True)
class ComponentFinding:
    """An unresolved or removed component at one canonical field path."""

    field: str
    component_kind: str
    component_id: int | str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "component_kind": self.component_kind,
            "component_id": self.component_id,
        }


@dataclass(frozen=True)
class BuildAudit:
    """Deterministic output of the build audit layer."""

    schema_version: int
    build_id: str
    status: str
    legality: str
    game_build_id: int | None
    checked_at: str
    missing_fields: tuple[str, ...]
    unknown_components: tuple[ComponentFinding, ...]
    removed_components: tuple[ComponentFinding, ...]
    affected_components: tuple[AffectedComponent, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "build_id": self.build_id,
            "status": self.status,
            "legality": self.legality,
            "game_build_id": self.game_build_id,
            "checked_at": self.checked_at,
            "missing_fields": list(self.missing_fields),
            "unknown_components": [
                item.to_dict() for item in self.unknown_components
            ],
            "removed_components": [
                item.to_dict() for item in self.removed_components
            ],
            "affected_components": [
                item.to_dict() for item in self.affected_components
            ],
            "warnings": list(self.warnings),
        }


def audit_build(
    build: BuildRecord,
    *,
    index: DatasetIndex,
    patch_events: Sequence[PatchEvent],
    checked_at: str,
) -> BuildAudit:
    """Audit one immutable canonical build against one indexed dataset."""

    checked_datetime = _parse_datetime(checked_at, "checked_at")
    missing: set[str] = set()
    warnings: set[str] = set()
    illegal: set[str] = set()
    components: list[tuple[str, str, ComponentRef]] = []

    _collect_core_components(build, components, missing)
    weapon_entries = _collect_equipment_components(
        build, index, components, missing, illegal
    )
    _check_specializations_and_traits(build, index, missing, illegal)
    _check_skills(build, index, illegal)

    unknown: list[ComponentFinding] = []
    removed: list[ComponentFinding] = []
    resolved: dict[str, Mapping[str, Any]] = {}
    for field, kind, component in components:
        identifier = component.id
        if not isinstance(identifier, int) or isinstance(identifier, bool):
            unknown.append(ComponentFinding(field, kind, identifier))
            continue
        entity = index.entity(kind, identifier)
        if entity is None:
            unknown.append(ComponentFinding(field, kind, identifier))
            continue
        resolved[field] = entity
        if _is_removed(entity):
            removed.append(ComponentFinding(field, kind, identifier))
    _check_equipment_semantics(resolved, illegal)
    _check_weapons(build, weapon_entries, resolved, index, illegal)

    for path in sorted(missing):
        warnings.add(f"missing required field: {path}")
    for finding in unknown:
        warnings.add(
            f"unknown {finding.component_kind} component at "
            f"{finding.field}: {finding.component_id}"
        )
    for finding in removed:
        warnings.add(
            f"removed {finding.component_kind} component at "
            f"{finding.field}: {finding.component_id}"
        )
    for message in illegal:
        warnings.add(message)
    if not index.dataset_build_matches:
        warnings.add("dataset game build is inconsistent")

    (
        content_dates,
        incomplete_sources,
        invalid_sources,
    ) = _source_content_dates_by_name(build)
    source_dates: dict[str, date] = {}
    source_date_missing = False
    source_date_ambiguous = False
    source_date_after_check = False
    for _, _, component in components:
        dates = content_dates.get(component.source)
        if (
            component.source in invalid_sources
            or (
                component.source in incomplete_sources
                and dates
            )
        ):
            source_date_ambiguous = True
        elif not dates:
            source_date_missing = True
        elif len(dates) != 1:
            source_date_ambiguous = True
        else:
            content_date = next(iter(dates))
            if content_date > checked_datetime.date():
                source_date_after_check = True
            else:
                source_dates[component.source] = content_date
    if source_date_missing:
        warnings.add("component source date is missing")
    if source_date_ambiguous:
        warnings.add("component source date is ambiguous")
    if source_date_after_check:
        warnings.add("component source date is after checked_at")
    source_date_unverifiable = (
        source_date_missing
        or source_date_ambiguous
        or source_date_after_check
    )

    affected: list[AffectedComponent] = []
    normalized_events = [
        event
        if isinstance(event, PatchEvent)
        else PatchEvent.from_dict(event)
        for event in patch_events
    ]
    for event in normalized_events:
        event_date = date.fromisoformat(event.effective_at)
        if event_date > checked_datetime.date():
            continue
        matching_components = [
            component
            for _, kind, component in components
            if kind == event.component_kind
            and component.id == event.component_id
        ]
        if any(
            source_dates.get(component.source) is not None
            and source_dates[component.source]
            < event_date
            <= checked_datetime.date()
            for component in matching_components
        ):
            affected.append(AffectedComponent.from_event(event))
    affected.sort(
        key=lambda item: (
            item.effective_at,
            item.component_kind,
            str(item.component_id),
            item.impact,
            item.change,
        )
    )
    for item in affected:
        warnings.add(
            f"post-source patch {item.effective_at} affects "
            f"{item.component_kind}:{item.component_id}"
        )

    unknown.sort(key=_finding_key)
    removed.sort(key=_finding_key)
    legality = "illegal" if illegal or removed else "legal"
    target_matches = (
        type(build.version_audit.get("game_build_id")) is int
        and build.version_audit.get("game_build_id") == index.game_build_id
    )
    publisher_claim = _publisher_claimed_current(build)
    provenance_conflicts = build.provenance.get("conflicts", ())
    has_provenance_conflicts = bool(provenance_conflicts)
    if has_provenance_conflicts:
        warnings.add("unresolved provenance conflicts require review")

    if legality == "illegal":
        status = "invalid"
    elif any(item.impact == "stale" for item in affected):
        status = "stale"
    elif (
        missing
        or unknown
        or has_provenance_conflicts
        or source_date_unverifiable
        or not index.dataset_build_matches
    ):
        status = "unverifiable"
    elif affected:
        status = "possibly_affected"
    elif target_matches:
        status = "current_verified"
    elif publisher_claim:
        status = "publisher_claimed_current"
    else:
        status = "unverifiable"

    return BuildAudit(
        schema_version=1,
        build_id=build.build_id,
        status=status,
        legality=legality,
        game_build_id=index.game_build_id,
        checked_at=checked_at,
        missing_fields=tuple(sorted(missing)),
        unknown_components=tuple(unknown),
        removed_components=tuple(removed),
        affected_components=tuple(affected),
        warnings=tuple(sorted(warnings)),
    )


def _collect_core_components(
    build: BuildRecord,
    components: list[tuple[str, str, ComponentRef]],
    missing: set[str],
) -> None:
    for index, specialization in enumerate(build.specializations):
        _add_component(
            components,
            missing,
            f"specializations[{index}]",
            "specialization",
            specialization,
        )
    for index in range(len(build.specializations), 3):
        missing.add(f"specializations[{index}]")
    for index, trait in enumerate(build.traits):
        _add_component(
            components,
            missing,
            f"traits[{index}]",
            "trait",
            trait,
        )
    for index in range(len(build.traits), 9):
        missing.add(f"traits[{index}]")
    _add_component(
        components, missing, "skills.heal", "skill", build.skills.get("heal")
    )
    utilities = build.skills.get("utilities", ())
    for index in range(3):
        value = (
            utilities[index]
            if isinstance(utilities, tuple) and index < len(utilities)
            else None
        )
        _add_component(
            components,
            missing,
            f"skills.utilities[{index}]",
            "skill",
            value,
        )
    _add_component(
        components,
        missing,
        "skills.elite",
        "skill",
        build.skills.get("elite"),
    )


def _collect_equipment_components(
    build: BuildRecord,
    dataset_index: DatasetIndex,
    components: list[tuple[str, str, ComponentRef]],
    missing: set[str],
    illegal: set[str],
) -> dict[str, Mapping[str, Any]]:
    for slot in _ARMOR_SLOTS:
        _add_component(
            components,
            missing,
            f"armor.{slot}",
            "equipment",
            build.armor.get(slot),
        )
    for slot in sorted(set(build.armor) - set(_ARMOR_SLOTS)):
        illegal.add(f"unsupported armor slot: {slot}")
    for slot in _TRINKET_SLOTS:
        _add_component(
            components,
            missing,
            f"trinkets.{slot}",
            "equipment",
            build.trinkets.get(slot),
        )
    for slot in sorted(set(build.trinkets) - set(_TRINKET_SLOTS)):
        illegal.add(f"unsupported trinket slot: {slot}")

    if len(build.runes) > 6:
        illegal.add("build has more than six rune slots")
    for index in range(6):
        value = build.runes[index] if index < len(build.runes) else None
        _add_component(
            components, missing, f"runes[{index}]", "upgrade", value
        )
    _add_component(
        components, missing, "relic", "upgrade", build.relic
    )
    _add_component(
        components,
        missing,
        "consumables.food",
        "consumable",
        build.consumables.get("food"),
    )
    _add_component(
        components,
        missing,
        "consumables.utility",
        "consumable",
        build.consumables.get("utility"),
    )

    entries: dict[str, Mapping[str, Any]] = {}
    for position, weapon in enumerate(build.weapons):
        slot = weapon.get("slot")
        if not isinstance(slot, str):
            missing.add(f"weapons[{position}].slot")
            continue
        if slot not in _WEAPON_SLOTS:
            illegal.add(f"unsupported weapon slot: {slot}")
            continue
        if slot in entries:
            illegal.add(f"duplicate weapon slot: {slot}")
            continue
        entries[slot] = weapon
    for main_slot, offhand_slot in (("w11", "w12"), ("w21", "w22")):
        main = entries.get(main_slot)
        offhand = entries.get(offhand_slot)
        if main is None:
            missing.add(f"weapons.{main_slot}")
            if offhand is None:
                missing.add(f"weapons.{offhand_slot}")
            else:
                _collect_weapon_entry(
                    offhand_slot,
                    offhand,
                    expected_sigils=1,
                    index=dataset_index,
                    components=components,
                    missing=missing,
                    illegal=illegal,
                )
            continue
        main_entity = _resolved_component(
            dataset_index, "equipment", main.get("item")
        )
        main_type = _equipment_weapon_type(main_entity)
        two_handed = main_type in _TWO_HANDED_WEAPONS
        _collect_weapon_entry(
            main_slot,
            main,
            expected_sigils=2 if two_handed else 1,
            index=dataset_index,
            components=components,
            missing=missing,
            illegal=illegal,
        )
        if two_handed:
            if offhand is not None:
                illegal.add(
                    f"two-handed weapon at {main_slot} cannot use {offhand_slot}"
                )
                _collect_weapon_entry(
                    offhand_slot,
                    offhand,
                    expected_sigils=1,
                    index=dataset_index,
                    components=components,
                    missing=missing,
                    illegal=illegal,
                )
        elif offhand is None:
            missing.add(f"weapons.{offhand_slot}")
        else:
            _collect_weapon_entry(
                offhand_slot,
                offhand,
                expected_sigils=1,
                index=dataset_index,
                components=components,
                missing=missing,
                illegal=illegal,
            )

    required_infusions = 0
    for slot in _ARMOR_SLOTS:
        required_infusions += _infusion_slot_count(
            _resolved_component(
                dataset_index, "equipment", build.armor.get(slot)
            )
        )
    for slot in _TRINKET_SLOTS:
        required_infusions += _infusion_slot_count(
            _resolved_component(
                dataset_index, "equipment", build.trinkets.get(slot)
            )
        )
    for weapon in entries.values():
        required_infusions += _infusion_slot_count(
            _resolved_component(
                dataset_index, "equipment", weapon.get("item")
            )
        )
    if len(build.infusions) > required_infusions:
        illegal.add("build has more infusions than resolved equipment slots")
    for position in range(required_infusions):
        value = (
            build.infusions[position]
            if position < len(build.infusions)
            else None
        )
        _add_component(
            components,
            missing,
            f"infusions[{position}]",
            "upgrade",
            value,
        )
    return entries


def _collect_weapon_entry(
    slot: str,
    weapon: Mapping[str, Any],
    *,
    expected_sigils: int,
    index: DatasetIndex,
    components: list[tuple[str, str, ComponentRef]],
    missing: set[str],
    illegal: set[str],
) -> None:
    weapon_type = weapon.get("type")
    if not isinstance(weapon_type, ComponentRef) or weapon_type.id is None:
        missing.add(f"weapons.{slot}.type")
    elif weapon_type.name is None:
        components.append(
            (f"weapons.{slot}.type", "weapon_type", weapon_type)
        )
    _add_component(
        components,
        missing,
        f"weapons.{slot}.item",
        "equipment",
        weapon.get("item"),
    )
    upgrades = weapon.get("upgrades", ())
    if not isinstance(upgrades, tuple):
        upgrades = ()
    if len(upgrades) > expected_sigils:
        illegal.add(f"weapon at {slot} has too many sigils")
    for position in range(expected_sigils):
        component = upgrades[position] if position < len(upgrades) else None
        _add_component(
            components,
            missing,
            f"weapons.{slot}.upgrades[{position}]",
            "upgrade",
            component,
        )
    item = _resolved_component(index, "equipment", weapon.get("item"))
    expected_infusions = _infusion_slot_count(item)
    infusions = weapon.get("infusions", ())
    if not isinstance(infusions, tuple):
        infusions = ()
    if len(infusions) > expected_infusions:
        illegal.add(f"weapon at {slot} has too many infusions")
    for position in range(expected_infusions):
        component = infusions[position] if position < len(infusions) else None
        _add_component(
            components,
            missing,
            f"weapons.{slot}.infusions[{position}]",
            "upgrade",
            component,
        )


def _resolved_component(
    index: DatasetIndex, kind: str, value: Any
) -> Mapping[str, Any] | None:
    if not isinstance(value, ComponentRef) or type(value.id) is not int:
        return None
    return index.entity(kind, value.id)


def _infusion_slot_count(entity: Mapping[str, Any] | None) -> int:
    if entity is None:
        return 0
    payload = entity.get("payload", {})
    details = payload.get("details", {}) if isinstance(payload, Mapping) else {}
    slots = details.get("infusion_slots", ()) if isinstance(details, Mapping) else ()
    return len(slots) if isinstance(slots, (list, tuple)) else 0


def _equipment_weapon_type(
    entity: Mapping[str, Any] | None,
) -> str | None:
    if entity is None:
        return None
    payload = entity.get("payload", {})
    details = payload.get("details", {}) if isinstance(payload, Mapping) else {}
    value = details.get("type") if isinstance(details, Mapping) else None
    return _normalize_weapon_type(value) if isinstance(value, str) else None


def _add_component(
    components: list[tuple[str, str, ComponentRef]],
    missing: set[str],
    field: str,
    kind: str,
    value: Any,
) -> None:
    if not isinstance(value, ComponentRef) or value.id is None:
        missing.add(field)
        return
    components.append((field, kind, value))


def _check_specializations_and_traits(
    build: BuildRecord,
    index: DatasetIndex,
    missing: set[str],
    illegal: set[str],
) -> None:
    if len(build.specializations) > 3:
        illegal.add("build has more than three specialization lines")
    selected = {
        item.id for item in build.specializations if type(item.id) is int
    }
    if len(selected) != len(
        [item for item in build.specializations if type(item.id) is int]
    ):
        illegal.add("duplicate selected specialization")
    elite_count = 0
    for specialization in build.specializations:
        if type(specialization.id) is not int:
            continue
        entity = index.entity("specialization", specialization.id)
        payload = entity.get("payload", {}) if entity is not None else {}
        if isinstance(payload, Mapping) and payload.get("elite") is True:
            elite_count += 1
    if elite_count > 1:
        illegal.add("multiple elite specialization lines selected")
    selected_tiers: set[tuple[int, int]] = set()
    for trait in build.traits:
        if type(trait.id) is not int:
            continue
        entity = index.entity("trait", trait.id)
        if entity is None:
            continue
        payload = entity.get("payload", {})
        specialization = (
            payload.get("specialization")
            if isinstance(payload, Mapping)
            else None
        )
        tier = payload.get("tier") if isinstance(payload, Mapping) else None
        allowed = index.specialization_trait_tiers.get(
            specialization, {}
        ).get(tier, frozenset())
        if specialization not in selected or trait.id not in allowed:
            illegal.add(
                f"trait {trait.id} is not legal for the selected "
                f"specialization and tier"
            )
            continue
        key = (specialization, tier)
        if key in selected_tiers:
            illegal.add(
                f"multiple major traits selected for specialization "
                f"{specialization} tier {tier}"
            )
        selected_tiers.add(key)
    for position, specialization in enumerate(build.specializations[:3]):
        if type(specialization.id) is not int:
            continue
        if index.entity("specialization", specialization.id) is None:
            continue
        for tier in (1, 2, 3):
            if (specialization.id, tier) not in selected_tiers:
                missing.add(
                    f"specializations[{position}].traits.tier{tier}"
                )


def _check_skills(
    build: BuildRecord, index: DatasetIndex, illegal: set[str]
) -> None:
    expected: list[tuple[str, str, ComponentRef | None]] = [
        ("skills.heal", "Heal", build.skills.get("heal")),
        *[
            (f"skills.utilities[{position}]", "Utility", component)
            for position, component in enumerate(
                build.skills.get("utilities", ())
            )
        ],
        ("skills.elite", "Elite", build.skills.get("elite")),
    ]
    selected_specializations = {
        item.id for item in build.specializations if type(item.id) is int
    }
    utility_ids = [
        component.id
        for field, _, component in expected
        if isinstance(component, ComponentRef)
        and ".utilities[" in field
        and type(component.id) is int
    ]
    if len(utility_ids) != len(set(utility_ids)):
        illegal.add("duplicate land utility skill")
    selectable_skill_ids = frozenset(index.skill_palette.values())
    for field, expected_slot, component in expected:
        if not isinstance(component, ComponentRef) or type(component.id) is not int:
            continue
        entity = index.entity("skill", component.id)
        if entity is None:
            continue
        if component.id not in selectable_skill_ids:
            illegal.add(
                f"{field} uses non-selectable skill {component.id}"
            )
        payload = entity.get("payload", {})
        slot = payload.get("slot") if isinstance(payload, Mapping) else None
        if slot != expected_slot:
            illegal.add(
                f"{field} uses {slot or 'unknown'} skill {component.id}"
            )
        specialization = (
            payload.get("specialization")
            if isinstance(payload, Mapping)
            else None
        )
        if (
            type(specialization) is int
            and specialization not in selected_specializations
        ):
            illegal.add(
                f"{field} requires unselected specialization "
                f"{specialization}"
            )


def _check_equipment_semantics(
    resolved: Mapping[str, Mapping[str, Any]],
    illegal: set[str],
) -> None:
    for slot, expected_type in _ARMOR_TYPES.items():
        entity = resolved.get(f"armor.{slot}")
        if entity is not None and not _matches_armor(entity, expected_type):
            illegal.add(f"armor.{slot} has an incompatible equipment item")
    for slot in _TRINKET_SLOTS:
        entity = resolved.get(f"trinkets.{slot}")
        if entity is not None and not _matches_trinket(entity, slot):
            illegal.add(f"trinkets.{slot} has an incompatible equipment item")
    for position in range(6):
        entity = resolved.get(f"runes[{position}]")
        if entity is not None and not _matches_upgrade(entity, "Rune"):
            illegal.add(f"runes[{position}] is not a rune")
    relic = resolved.get("relic")
    if relic is not None and _payload_type(relic) != "Relic":
        illegal.add("relic does not reference a relic item")
    for slot, expected in (("food", "Food"), ("utility", "Utility")):
        entity = resolved.get(f"consumables.{slot}")
        if entity is not None and not _matches_consumable(entity, expected):
            illegal.add(f"consumables.{slot} has the wrong consumable type")
    for field, entity in resolved.items():
        if ".upgrades[" in field and not _matches_upgrade(entity, "Sigil"):
            illegal.add(f"{field} is not a sigil")
        if (
            (field.startswith("infusions[") or ".infusions[" in field)
            and not _matches_upgrade(entity, "Infusion")
        ):
            illegal.add(f"{field} is not an infusion")


def _check_weapons(
    build: BuildRecord,
    entries: Mapping[str, Mapping[str, Any]],
    resolved: Mapping[str, Mapping[str, Any]],
    index: DatasetIndex,
    illegal: set[str],
) -> None:
    selected_specializations = {
        item.id for item in build.specializations if type(item.id) is int
    }
    for slot, weapon in entries.items():
        component = weapon.get("type")
        if not isinstance(component, ComponentRef):
            continue
        item = resolved.get(f"weapons.{slot}.item")
        if item is not None and _payload_type(item) != "Weapon":
            illegal.add(f"weapons.{slot}.item is not a weapon")
        name = component.name
        if name is None:
            continue
        normalized_name = _normalize_weapon_type(name)
        availability = (
            index.profession_weapons.get(normalized_name)
            if isinstance(name, str)
            else None
        )
        if availability is None:
            illegal.add(f"weapon type is unavailable to Thief at {slot}: {name}")
            continue
        flags = availability.get("flags", ())
        if "Aquatic" in flags:
            illegal.add(f"weapon type {name} is aquatic-only at {slot}")
        is_main = slot in {"w11", "w21"}
        if is_main and not ({"Mainhand", "TwoHand"} & set(flags)):
            illegal.add(f"weapon type {name} cannot occupy {slot}")
        if not is_main and "Offhand" not in flags:
            illegal.add(f"weapon type {name} cannot occupy {slot}")
        specialization = availability.get("specialization")
        if (
            type(specialization) is int
            and specialization not in selected_specializations
        ):
            illegal.add(
                f"weapon type {name} requires unselected specialization "
                f"{specialization}"
            )
        item_type = _equipment_weapon_type(item)
        if item is not None and (
            item_type != normalized_name
        ):
            illegal.add(
                f"weapons.{slot}.item does not match weapon type {name}"
            )


def _matches_armor(entity: Mapping[str, Any], expected_type: str) -> bool:
    payload = entity.get("payload", {})
    details = payload.get("details", {}) if isinstance(payload, Mapping) else {}
    return (
        isinstance(payload, Mapping)
        and isinstance(details, Mapping)
        and payload.get("type") == "Armor"
        and details.get("weight_class") == "Medium"
        and details.get("type") == expected_type
    )


def _matches_trinket(entity: Mapping[str, Any], slot: str) -> bool:
    payload = entity.get("payload", {})
    details = payload.get("details", {}) if isinstance(payload, Mapping) else {}
    if not isinstance(payload, Mapping) or not isinstance(details, Mapping):
        return False
    if slot == "back":
        return payload.get("type") == "Back"
    return (
        payload.get("type") == "Trinket"
        and details.get("type") == _TRINKET_TYPES[slot]
    )


def _matches_upgrade(entity: Mapping[str, Any], expected: str) -> bool:
    payload = entity.get("payload", {})
    details = payload.get("details", {}) if isinstance(payload, Mapping) else {}
    return (
        isinstance(payload, Mapping)
        and isinstance(details, Mapping)
        and payload.get("type") == "UpgradeComponent"
        and details.get("type") == expected
    )


def _matches_consumable(
    entity: Mapping[str, Any], expected: str
) -> bool:
    payload = entity.get("payload", {})
    details = payload.get("details", {}) if isinstance(payload, Mapping) else {}
    return (
        isinstance(payload, Mapping)
        and isinstance(details, Mapping)
        and payload.get("type") == "Consumable"
        and details.get("type") == expected
    )


def _payload_type(entity: Mapping[str, Any]) -> Any:
    payload = entity.get("payload", {})
    return payload.get("type") if isinstance(payload, Mapping) else None


def _normalize_weapon_type(value: str) -> str:
    return _WEAPON_TYPE_NORMALIZATION.get(value, value)


def _is_removed(entity: Mapping[str, Any]) -> bool:
    payload = entity.get("payload", {})
    return (
        entity.get("verification_status") == "removed"
        or (
            isinstance(payload, Mapping)
            and (
                payload.get("removed") is True
                or payload.get("deleted") is True
                or payload.get("available") is False
            )
        )
    )


def _source_content_dates_by_name(
    build: BuildRecord,
) -> tuple[
    dict[str, frozenset[date]],
    frozenset[str],
    frozenset[str],
]:
    found: dict[str, set[date]] = {}
    incomplete_sources: set[str] = set()
    invalid_sources: set[str] = set()
    sources = build.provenance.get("sources", ())
    if not isinstance(sources, tuple):
        return {}, frozenset(), frozenset()
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        source_name = source.get("source")
        if not isinstance(source_name, str):
            continue
        dates = found.setdefault(source_name, set())
        record_dates: set[date] = set()
        accepted_field_seen = False
        for field in ("effective_patch", "updated_at", "published_at"):
            if field not in source:
                continue
            accepted_field_seen = True
            parsed = _optional_date(source[field])
            if parsed is None:
                invalid_sources.add(source_name)
            else:
                record_dates.add(parsed)
        if not accepted_field_seen:
            incomplete_sources.add(source_name)
        elif len(record_dates) != 1:
            invalid_sources.add(source_name)
        dates.update(record_dates)
    return (
        {
            source_name: frozenset(dates)
            for source_name, dates in found.items()
        },
        frozenset(incomplete_sources),
        frozenset(invalid_sources),
    )


def _optional_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    if (
        len(value) < 10
        or value[4] != "-"
        or value[7] != "-"
        or not (value[:4] + value[5:7] + value[8:10]).isdigit()
    ):
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        if len(value) <= 10 or value[10] != "T":
            return None
        if _ISO_TIMEZONE_SUFFIX.search(value) is None:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.date()
    except ValueError:
        return None


def _publisher_claimed_current(build: BuildRecord) -> bool:
    if build.version_audit.get("status") == "publisher_claimed_current":
        return True
    sources = build.provenance.get("sources", ())
    return isinstance(sources, tuple) and any(
        isinstance(source, Mapping)
        and source.get("publisher_status") == "publisher_claimed_current"
        for source in sources
    )


def _parse_datetime(value: str, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO 8601 date-time")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"{label} must be an ISO 8601 date-time"
        ) from error


def _finding_key(
    finding: ComponentFinding,
) -> tuple[str, str, str]:
    return (
        finding.field,
        finding.component_kind,
        str(finding.component_id),
    )
