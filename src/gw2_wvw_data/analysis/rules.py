"""Validated immutable project-authored analysis rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gw2_wvw_data.contracts import schema_errors


@dataclass(frozen=True)
class ComponentSelector:
    component_id: int | str
    component_kind: str | None = None
    field: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ComponentSelector:
        return cls(
            component_id=value["component_id"],
            component_kind=value.get("component_kind"),
            field=value.get("field"),
        )

    def to_dict(self, *, require_kind: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "component_kind": self.component_kind,
            "component_id": self.component_id,
            "field": self.field,
        }
        if not require_kind:
            return {key: item for key, item in value.items() if item is not None}
        return value


@dataclass(frozen=True)
class EvidenceSpec:
    component_id: int | str
    field: str
    component_kind: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EvidenceSpec:
        return cls(
            component_id=value["component_id"],
            field=value["field"],
            component_kind=value.get("component_kind"),
        )


@dataclass(frozen=True)
class RuleEffect:
    dimension: str
    delta: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuleEffect:
        return cls(dimension=value["dimension"], delta=value["delta"])


@dataclass(frozen=True)
class AnalysisRule:
    rule_id: str
    when: ComponentSelector
    effects: tuple[RuleEffect, ...]
    evidence: tuple[EvidenceSpec, ...]
    claim: str


@dataclass(frozen=True)
class ImprovementRule:
    improvement_id: str
    replace: ComponentSelector
    with_: ComponentSelector
    benefit: str
    cost: str
    applies_when: tuple[ComponentSelector, ...]
    evidence: tuple[EvidenceSpec, ...]


@dataclass(frozen=True)
class RuleSet:
    schema_version: int
    ruleset_id: str
    dimensions: tuple[str, ...]
    rules: tuple[AnalysisRule, ...]
    improvements: tuple[ImprovementRule, ...]


def load_rules(path: str | Path) -> RuleSet:
    """Load, schema-check, and freeze one project-authored rule file."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"analysis rules are unreadable: {error}") from error
    errors = schema_errors(value, "analysis-rules.schema.json")
    if errors:
        raise ValueError(f"analysis rules schema invalid: {errors[0]}")

    rule_ids = [item["rule_id"] for item in value["rules"]]
    duplicate_rule = _first_duplicate(rule_ids)
    if duplicate_rule is not None:
        raise ValueError(f"duplicate rule_id: {duplicate_rule}")
    raw_improvements = value.get("improvements", [])
    improvement_ids = [
        item["improvement_id"] for item in raw_improvements
    ]
    duplicate_improvement = _first_duplicate(improvement_ids)
    if duplicate_improvement is not None:
        raise ValueError(
            f"duplicate improvement_id: {duplicate_improvement}"
        )

    improvements: list[ImprovementRule] = []
    for item in raw_improvements:
        replace = ComponentSelector.from_dict(item["replace"])
        with_ = ComponentSelector.from_dict(item["with"])
        if (
            replace.component_kind is not None
            and with_.component_kind is not None
            and replace.component_kind != with_.component_kind
        ):
            raise ValueError(
                f"improvement {item['improvement_id']} changes component kind"
            )
        raw_applies = item["applies_when"]
        applies = raw_applies if isinstance(raw_applies, list) else [raw_applies]
        improvements.append(
            ImprovementRule(
                improvement_id=item["improvement_id"],
                replace=replace,
                with_=with_,
                benefit=item["benefit"],
                cost=item["cost"],
                applies_when=tuple(
                    ComponentSelector.from_dict(selector)
                    for selector in applies
                ),
                evidence=tuple(
                    EvidenceSpec.from_dict(evidence)
                    for evidence in item["evidence"]
                ),
            )
        )

    rules = tuple(
        AnalysisRule(
            rule_id=item["rule_id"],
            when=ComponentSelector.from_dict(item["when"]),
            effects=tuple(
                RuleEffect.from_dict(effect) for effect in item["effects"]
            ),
            evidence=tuple(
                EvidenceSpec.from_dict(evidence)
                for evidence in item["evidence"]
            ),
            claim=item["claim"],
        )
        for item in value["rules"]
    )
    return RuleSet(
        schema_version=value["schema_version"],
        ruleset_id=value["ruleset_id"],
        dimensions=tuple(value["dimensions"]),
        rules=rules,
        improvements=tuple(improvements),
    )


def _first_duplicate(values: list[str]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None
