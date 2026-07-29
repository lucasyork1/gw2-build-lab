"""Deterministic evidence-backed capability analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from gw2_wvw_data.analysis.rules import (
    AnalysisRule,
    ComponentSelector,
    EvidenceSpec,
    ImprovementRule,
    RuleSet,
)
from gw2_wvw_data.audit import BuildAudit, DatasetIndex
from gw2_wvw_data.builds.model import BuildRecord, ComponentRef


_BAND_LABELS = {
    1: "very_low",
    2: "low",
    3: "medium",
    4: "high",
    5: "very_high",
}
_EQUIPMENT_CONFIDENCE_DIMENSIONS = {
    "weapons": frozenset(
        {"burst_damage", "sustained_damage", "control_interrupt"}
    ),
    "armor": frozenset(
        {
            "burst_damage",
            "sustained_damage",
            "survival_recovery",
            "condition_cleanse",
        }
    ),
    "trinkets": frozenset(
        {
            "burst_damage",
            "sustained_damage",
            "survival_recovery",
            "condition_cleanse",
        }
    ),
    "runes": frozenset(
        {
            "burst_damage",
            "sustained_damage",
            "survival_recovery",
            "condition_cleanse",
        }
    ),
    "relic": frozenset(
        {
            "burst_damage",
            "sustained_damage",
            "survival_recovery",
            "condition_cleanse",
        }
    ),
    "infusions": frozenset(
        {"burst_damage", "sustained_damage", "survival_recovery"}
    ),
    "consumables": frozenset(
        {
            "burst_damage",
            "sustained_damage",
            "survival_recovery",
            "condition_cleanse",
        }
    ),
}
_PATH_PART = re.compile(r"([^.[]+)|\[(\d+)\]")


@dataclass(frozen=True, order=True)
class EvidenceReference:
    component_kind: str
    component_id: int | str
    field: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_kind": self.component_kind,
            "component_id": self.component_id,
            "field": self.field,
        }


@dataclass(frozen=True)
class DimensionAnalysis:
    band: int
    label: str
    confidence: str
    confidence_reasons: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "label": self.label,
            "confidence": self.confidence,
            "confidence_reasons": list(self.confidence_reasons),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class AnalysisConclusion:
    rule_id: str
    claim: str
    evidence: tuple[EvidenceReference, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "claim": self.claim,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class ImprovementAnalysis:
    improvement_id: str
    replace: ComponentSelector
    with_: ComponentSelector
    benefit: str
    cost: str
    applies_when: tuple[ComponentSelector, ...]
    evidence: tuple[EvidenceReference, ...]
    derived_build: BuildRecord

    def to_dict(self) -> dict[str, Any]:
        return {
            "improvement_id": self.improvement_id,
            "replace": self.replace.to_dict(require_kind=True),
            "with": self.with_.to_dict(require_kind=True),
            "benefit": self.benefit,
            "cost": self.cost,
            "applies_when": [
                item.to_dict(require_kind=True) for item in self.applies_when
            ],
            "evidence": [item.to_dict() for item in self.evidence],
            "derived_build": self.derived_build.to_dict(),
        }


@dataclass(frozen=True)
class BuildAnalysis:
    schema_version: int
    build_id: str
    ruleset_id: str
    dimensions: Mapping[str, DimensionAnalysis]
    strengths: tuple[AnalysisConclusion, ...]
    weaknesses: tuple[AnalysisConclusion, ...]
    improvements: tuple[ImprovementAnalysis, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "build_id": self.build_id,
            "ruleset_id": self.ruleset_id,
            "dimensions": {
                name: item.to_dict()
                for name, item in self.dimensions.items()
            },
            "strengths": [item.to_dict() for item in self.strengths],
            "weaknesses": [item.to_dict() for item in self.weaknesses],
            "improvements": [
                item.to_dict() for item in self.improvements
            ],
        }


@dataclass(frozen=True)
class _BuildComponent:
    field: str
    component_kind: str
    component: ComponentRef


def analyze_build(
    build: BuildRecord,
    audit: BuildAudit,
    *,
    index: DatasetIndex,
    rules: RuleSet,
) -> BuildAnalysis:
    """Apply only validated project rules to canonical component IDs."""

    if audit.build_id != build.build_id:
        raise ValueError("audit build_id does not match build")
    components = tuple(_build_components(build))
    bands = {dimension: 3 for dimension in rules.dimensions}
    reasons: dict[str, set[str]] = {
        dimension: set() for dimension in rules.dimensions
    }
    dimension_evidence: dict[str, set[EvidenceReference]] = {
        dimension: set() for dimension in rules.dimensions
    }
    strengths: list[AnalysisConclusion] = []
    weaknesses: list[AnalysisConclusion] = []

    for rule in sorted(rules.rules, key=lambda item: item.rule_id):
        if not _selector_matches(rule.when, components):
            continue
        evidence, missing_reason = _resolve_evidence(
            rule.evidence,
            index=index,
            components=components,
            fallback_kind=rule.when.component_kind,
            require_in_build=True,
        )
        if missing_reason is not None:
            for effect in rule.effects:
                reasons[effect.dimension].add(
                    f"rule {rule.rule_id} skipped: {missing_reason}"
                )
            continue
        for effect in rule.effects:
            bands[effect.dimension] += effect.delta
            dimension_evidence[effect.dimension].update(evidence)
        conclusion = AnalysisConclusion(
            rule_id=rule.rule_id,
            claim=rule.claim,
            evidence=evidence,
        )
        if any(_is_strength(effect.dimension, effect.delta) for effect in rule.effects):
            strengths.append(conclusion)
        if any(_is_weakness(effect.dimension, effect.delta) for effect in rule.effects):
            weaknesses.append(conclusion)

    _apply_equipment_confidence(audit, reasons)
    dimensions: dict[str, DimensionAnalysis] = {}
    for name in rules.dimensions:
        dimension_reasons = tuple(sorted(reasons[name]))
        band = max(1, min(5, bands[name]))
        dimensions[name] = DimensionAnalysis(
            band=band,
            label=_BAND_LABELS[band],
            confidence="low" if dimension_reasons else "high",
            confidence_reasons=dimension_reasons,
            evidence=tuple(
                sorted(
                    dimension_evidence[name],
                    key=_evidence_sort_key,
                )
            ),
        )

    improvements = _applicable_improvements(
        build,
        rules=rules,
        index=index,
        components=components,
    )
    return BuildAnalysis(
        schema_version=1,
        build_id=build.build_id,
        ruleset_id=rules.ruleset_id,
        dimensions=MappingProxyType(dimensions),
        strengths=tuple(strengths),
        weaknesses=tuple(weaknesses),
        improvements=improvements,
    )


def _apply_equipment_confidence(
    audit: BuildAudit, reasons: dict[str, set[str]]
) -> None:
    for field in audit.missing_fields:
        prefix = field.split(".", 1)[0].split("[", 1)[0]
        for dimension in _EQUIPMENT_CONFIDENCE_DIMENSIONS.get(prefix, ()):
            reasons[dimension].add(
                f"missing equipment field {field} limits confidence"
            )


def _applicable_improvements(
    build: BuildRecord,
    *,
    rules: RuleSet,
    index: DatasetIndex,
    components: tuple[_BuildComponent, ...],
) -> tuple[ImprovementAnalysis, ...]:
    results: list[ImprovementAnalysis] = []
    for rule in sorted(
        rules.improvements, key=lambda item: item.improvement_id
    ):
        if not all(
            _selector_matches(selector, components)
            for selector in rule.applies_when
        ):
            continue
        matching = _matching_components(rule.replace, components)
        if not matching:
            continue
        evidence, missing_reason = _resolve_evidence(
            rule.evidence,
            index=index,
            components=components,
            fallback_kind=rule.replace.component_kind,
        )
        if missing_reason is not None:
            continue
        replace_kind = (
            rule.replace.component_kind or matching[0].component_kind
        )
        with_kind = rule.with_.component_kind or replace_kind
        entity = index.entity(with_kind, rule.with_.component_id)
        if entity is None:
            continue
        field = rule.replace.field or matching[0].field
        value = build.to_dict()
        replacement = {
            "id": rule.with_.component_id,
            "name": _entity_name(entity),
            "source": f"analysis-rules:{rules.ruleset_id}",
            "confidence": "mapped",
        }
        if not _set_path(value, field, replacement):
            continue
        value["build_id"] = (
            f"{build.build_id}--{rule.improvement_id}"
        )
        derived = BuildRecord.from_dict(value)
        results.append(
            ImprovementAnalysis(
                improvement_id=rule.improvement_id,
                replace=ComponentSelector(
                    component_kind=replace_kind,
                    component_id=rule.replace.component_id,
                    field=field,
                ),
                with_=ComponentSelector(
                    component_kind=with_kind,
                    component_id=rule.with_.component_id,
                    field=field,
                ),
                benefit=rule.benefit,
                cost=rule.cost,
                applies_when=tuple(
                    ComponentSelector(
                        component_kind=(
                            selector.component_kind
                            or _matching_components(
                                selector, components
                            )[0].component_kind
                        ),
                        component_id=selector.component_id,
                        field=selector.field,
                    )
                    for selector in rule.applies_when
                ),
                evidence=evidence,
                derived_build=derived,
            )
        )
    return tuple(results)


def _resolve_evidence(
    specs: tuple[EvidenceSpec, ...],
    *,
    index: DatasetIndex,
    components: tuple[_BuildComponent, ...],
    fallback_kind: str | None,
    require_in_build: bool = False,
) -> tuple[tuple[EvidenceReference, ...], str | None]:
    resolved: set[EvidenceReference] = set()
    for spec in specs:
        kind = spec.component_kind or fallback_kind
        if kind is None:
            component_kinds = {
                item.component_kind
                for item in components
                if item.component.id == spec.component_id
            }
            if len(component_kinds) == 1:
                kind = next(iter(component_kinds))
            else:
                index_kinds = {
                    item_kind
                    for item_kind, identifier in index.entities
                    if identifier == spec.component_id
                }
                if len(index_kinds) == 1:
                    kind = next(iter(index_kinds))
        if kind is None:
            return (), (
                f"component kind is ambiguous for {spec.component_id}"
            )
        if require_in_build and not any(
            item.component_kind == kind
            and item.component.id == spec.component_id
            for item in components
        ):
            return (), (
                f"{kind}:{spec.component_id} is not selected in the build"
            )
        entity = index.entity(kind, spec.component_id)
        if entity is None:
            return (), f"missing {kind}:{spec.component_id}"
        if not _field_exists(entity, spec.field):
            return (), (
                f"missing field {spec.field} on "
                f"{kind}:{spec.component_id}"
            )
        resolved.add(
            EvidenceReference(
                component_kind=kind,
                component_id=spec.component_id,
                field=spec.field,
            )
        )
    return (
        tuple(sorted(resolved, key=_evidence_sort_key)),
        None,
    )


def _field_exists(value: Any, field: str) -> bool:
    current = value
    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _selector_matches(
    selector: ComponentSelector,
    components: tuple[_BuildComponent, ...],
) -> bool:
    return bool(_matching_components(selector, components))


def _matching_components(
    selector: ComponentSelector,
    components: tuple[_BuildComponent, ...],
) -> tuple[_BuildComponent, ...]:
    return tuple(
        item
        for item in components
        if item.component.id == selector.component_id
        and (
            selector.component_kind is None
            or item.component_kind == selector.component_kind
        )
        and (selector.field is None or item.field == selector.field)
    )


def _build_components(build: BuildRecord) -> Iterable[_BuildComponent]:
    for position, component in enumerate(build.specializations):
        yield _BuildComponent(
            f"specializations[{position}]", "specialization", component
        )
    for position, component in enumerate(build.traits):
        yield _BuildComponent(f"traits[{position}]", "trait", component)
    heal = build.skills.get("heal")
    if isinstance(heal, ComponentRef):
        yield _BuildComponent("skills.heal", "skill", heal)
    utilities = build.skills.get("utilities", ())
    if isinstance(utilities, tuple):
        for position, component in enumerate(utilities):
            if isinstance(component, ComponentRef):
                yield _BuildComponent(
                    f"skills.utilities[{position}]", "skill", component
                )
    elite = build.skills.get("elite")
    if isinstance(elite, ComponentRef):
        yield _BuildComponent("skills.elite", "skill", elite)
    for position, weapon in enumerate(build.weapons):
        slot = weapon.get("slot")
        prefix = (
            f"weapons.{slot}"
            if isinstance(slot, str)
            else f"weapons[{position}]"
        )
        yield from _mapping_component(
            prefix + ".type", weapon.get("type"), "weapon_type"
        )
        yield from _mapping_component(prefix + ".item", weapon.get("item"), "equipment")
        for group, kind in (("upgrades", "upgrade"), ("infusions", "upgrade")):
            values = weapon.get(group, ())
            if isinstance(values, tuple):
                for item_position, component in enumerate(values):
                    yield from _mapping_component(
                        f"{prefix}.{group}[{item_position}]",
                        component,
                        kind,
                    )
    for group, values in (("armor", build.armor), ("trinkets", build.trinkets)):
        for slot, component in values.items():
            yield from _mapping_component(
                f"{group}.{slot}", component, "equipment"
            )
    for position, component in enumerate(build.runes):
        yield from _mapping_component(
            f"runes[{position}]", component, "upgrade"
        )
    yield from _mapping_component("relic", build.relic, "upgrade")
    for position, component in enumerate(build.infusions):
        yield from _mapping_component(
            f"infusions[{position}]", component, "upgrade"
        )
    for slot, component in build.consumables.items():
        yield from _mapping_component(
            f"consumables.{slot}", component, "consumable"
        )


def _mapping_component(
    field: str, value: Any, kind: str
) -> Iterable[_BuildComponent]:
    if isinstance(value, ComponentRef):
        yield _BuildComponent(field, kind, value)


def _set_path(value: dict[str, Any], path: str, replacement: Any) -> bool:
    parts: list[str | int] = []
    for match in _PATH_PART.finditer(path):
        key, index = match.groups()
        parts.append(key if key is not None else int(index))
    if not parts:
        return False
    current: Any = value
    for part in parts[:-1]:
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return False
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
    final = parts[-1]
    if isinstance(final, int):
        if not isinstance(current, list) or final >= len(current):
            return False
        current[final] = replacement
    else:
        if not isinstance(current, dict) or final not in current:
            return False
        current[final] = replacement
    return True


def _entity_name(entity: Mapping[str, Any]) -> str | None:
    names = entity.get("names")
    if isinstance(names, Mapping) and isinstance(names.get("en"), str):
        return names["en"]
    return None


def _evidence_sort_key(
    item: EvidenceReference,
) -> tuple[str, int, int | str, str]:
    identifier = item.component_id
    return (
        item.component_kind,
        0 if isinstance(identifier, int) else 1,
        identifier,
        item.field,
    )


def _is_strength(dimension: str, delta: int) -> bool:
    if dimension == "operation_difficulty":
        return delta < 0
    return delta > 0


def _is_weakness(dimension: str, delta: int) -> bool:
    if dimension == "operation_difficulty":
        return delta > 0
    return delta < 0
