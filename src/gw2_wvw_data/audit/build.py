"""Completeness, legality, resolution, and freshness checks for builds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

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

    _parse_datetime(checked_at, "checked_at")
    missing: set[str] = set()
    warnings: set[str] = set()
    illegal: set[str] = set()
    components: list[tuple[str, str, ComponentRef]] = []

    _collect_core_components(build, components, missing)
    weapon_entries = _collect_equipment_components(
        build, components, missing, illegal
    )
    _check_specializations_and_traits(build, index, illegal)
    _check_skills(build, index, illegal)
    _check_weapons(build, weapon_entries, index, illegal)

    unknown: list[ComponentFinding] = []
    removed: list[ComponentFinding] = []
    referenced_keys: set[tuple[str, int | str]] = set()
    for field, kind, component in components:
        identifier = component.id
        if not isinstance(identifier, int) or isinstance(identifier, bool):
            unknown.append(ComponentFinding(field, kind, identifier))
            continue
        entity = index.entity(kind, identifier)
        if entity is None:
            unknown.append(ComponentFinding(field, kind, identifier))
            continue
        referenced_keys.add((kind, identifier))
        if _is_removed(entity):
            removed.append(ComponentFinding(field, kind, identifier))

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

    source_date = _latest_source_date(build)
    affected: list[AffectedComponent] = []
    if source_date is not None:
        normalized_events = [
            event
            if isinstance(event, PatchEvent)
            else PatchEvent.from_dict(event)
            for event in patch_events
        ]
        for event in normalized_events:
            if (
                (event.component_kind, event.component_id) in referenced_keys
                and date.fromisoformat(event.effective_at) > source_date
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

    if legality == "illegal":
        status = "invalid"
    elif any(item.impact == "stale" for item in affected):
        status = "stale"
    elif missing or unknown or not index.dataset_build_matches:
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
    for index in range(3):
        if index >= len(build.specializations):
            missing.add(f"specializations[{index}]")
        else:
            _add_component(
                components,
                missing,
                f"specializations[{index}]",
                "specialization",
                build.specializations[index],
            )
    for index in range(9):
        if index >= len(build.traits):
            missing.add(f"traits[{index}]")
        else:
            _add_component(
                components,
                missing,
                f"traits[{index}]",
                "trait",
                build.traits[index],
            )
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
        if not isinstance(slot, str) and position < len(_WEAPON_SLOTS):
            slot = _WEAPON_SLOTS[position]
        if slot not in _WEAPON_SLOTS:
            illegal.add(f"unsupported weapon slot: {slot}")
            continue
        if slot in entries:
            illegal.add(f"duplicate weapon slot: {slot}")
            continue
        entries[slot] = weapon
    for slot in _WEAPON_SLOTS:
        weapon = entries.get(slot)
        if weapon is None:
            missing.add(f"weapons.{slot}")
            continue
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
        if isinstance(upgrades, tuple):
            for index, component in enumerate(upgrades):
                _add_component(
                    components,
                    missing,
                    f"weapons.{slot}.upgrades[{index}]",
                    "upgrade",
                    component,
                )
        infusions = weapon.get("infusions", ())
        if isinstance(infusions, tuple):
            for index, component in enumerate(infusions):
                _add_component(
                    components,
                    missing,
                    f"weapons.{slot}.infusions[{index}]",
                    "upgrade",
                    component,
                )
    for index, component in enumerate(build.infusions):
        _add_component(
            components,
            missing,
            f"infusions[{index}]",
            "upgrade",
            component,
        )
    return entries


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
    build: BuildRecord, index: DatasetIndex, illegal: set[str]
) -> None:
    selected = {
        item.id for item in build.specializations if type(item.id) is int
    }
    if len(selected) != len(
        [item for item in build.specializations if type(item.id) is int]
    ):
        illegal.add("duplicate selected specialization")
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
    for field, expected_slot, component in expected:
        if not isinstance(component, ComponentRef) or type(component.id) is not int:
            continue
        entity = index.entity("skill", component.id)
        if entity is None:
            continue
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


def _check_weapons(
    build: BuildRecord,
    entries: Mapping[str, Mapping[str, Any]],
    index: DatasetIndex,
    illegal: set[str],
) -> None:
    selected_specializations = {
        item.id for item in build.specializations if type(item.id) is int
    }
    for slot, weapon in entries.items():
        component = weapon.get("type")
        if not isinstance(component, ComponentRef):
            illegal.add(f"weapon type is missing at {slot}")
            continue
        name = component.name
        if name is None:
            continue
        availability = (
            index.profession_weapons.get(name)
            if isinstance(name, str)
            else None
        )
        if availability is None:
            illegal.add(f"weapon type is unavailable to Thief at {slot}: {name}")
            continue
        flags = availability.get("flags", ())
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


def _latest_source_date(build: BuildRecord) -> date | None:
    found: list[date] = []
    sources = build.provenance.get("sources", ())
    if not isinstance(sources, tuple):
        return None
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for field in ("updated_at", "published_at", "effective_patch"):
            parsed = _optional_date(source.get(field))
            if parsed is not None:
                found.append(parsed)
    return max(found) if found else None


def _optional_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
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
