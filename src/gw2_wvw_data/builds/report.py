"""Deterministic player-readable build analysis reports."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from gw2_wvw_data.analysis import (
    BuildAnalysis,
    BuildComparison,
    EvidenceReference,
)
from gw2_wvw_data.audit import BuildAudit
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


def render_markdown(
    build: BuildRecord,
    audit: BuildAudit,
    analysis: BuildAnalysis,
) -> str:
    """Render a complete deterministic Markdown report without inference."""

    if audit.build_id != build.build_id:
        raise ValueError("audit build_id does not match build")
    if analysis.build_id != build.build_id:
        raise ValueError("analysis build_id does not match build")

    lines = [
        "# WvW Thief Build Analysis",
        "",
        "## Identity",
        "",
        f"- Build ID: {_text(build.build_id)}",
        f"- Profession: {_text(build.profession)}",
        f"- Mode: {_text(build.mode)}",
        f"- Context: {_joined(build.context)}",
        "",
        "## Completeness",
        "",
        (
            "- Status: Complete"
            if not audit.missing_fields
            else (
                f"- Status: Incomplete "
                f"({len(audit.missing_fields)} missing fields)"
            )
        ),
        "- Missing fields: "
        + (
            ", ".join(_text(item) for item in audit.missing_fields)
            if audit.missing_fields
            else "None"
        ),
        "",
        "## Version Status",
        "",
        f"- Status: {_text(audit.status)}",
        f"- Dataset game build: {_display(audit.game_build_id)}",
        f"- Checked at: {_display(audit.checked_at)}",
        "",
        "## Legality",
        "",
        f"- Status: {_text(audit.legality)}",
        "",
        "## Equipment",
        "",
        "| Slot | Value |",
        "| --- | --- |",
        *_equipment_rows(build),
        "",
        "## Capability Dimensions",
        "",
        "| Dimension | Band | Label | Confidence | Evidence |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for name, dimension in analysis.dimensions.items():
        lines.append(
            "| "
            + " | ".join(
                (
                    _text(name),
                    str(dimension.band),
                    _text(dimension.label),
                    _text(dimension.confidence),
                    str(len(dimension.evidence)),
                )
            )
            + " |"
        )

    lines.extend(["", "## Strengths", ""])
    lines.extend(_conclusion_lines(analysis.strengths))
    lines.extend(["", "## Weaknesses", ""])
    lines.extend(_conclusion_lines(analysis.weaknesses))
    lines.extend(["", "## Risks", ""])
    lines.extend(_risk_lines(audit))
    lines.extend(["", "## Improvements", ""])
    if analysis.improvements:
        for improvement in analysis.improvements:
            lines.extend(
                [
                    f"### {_text(improvement.improvement_id)}",
                    "",
                    f"- Replace: {_selector(improvement.replace)}",
                    f"- With: {_selector(improvement.with_)}",
                    f"- Benefit: {_text(improvement.benefit)}",
                    f"- Cost: {_text(improvement.cost)}",
                    (
                        "- Applies when: "
                        + ", ".join(
                            _selector(item) for item in improvement.applies_when
                        )
                    ),
                    (
                        "- Derived build: "
                        f"{_text(improvement.derived_build.build_id)}"
                    ),
                    "",
                ]
            )
    else:
        lines.append("- None")
    if analysis.improvement_reasons:
        lines.extend(
            [
                "",
                "### Unavailable Improvements",
                "",
                *(
                    f"- {_text(item.improvement_id)}: {_text(item.reason)}"
                    for item in analysis.improvement_reasons
                ),
            ]
        )

    lines.extend(["", "## Evidence", ""])
    evidence = _all_evidence(analysis)
    lines.extend(
        (
            f"- {_text(item.component_kind)}:{_text(item.component_id)} "
            f"field {_text(item.field)}"
            for item in evidence
        )
        if evidence
        else ("- None",)
    )

    lines.extend(["", "## Sources", ""])
    sources = build.provenance.get("sources", ())
    if isinstance(sources, tuple) and sources:
        lines.extend(f"- {_source(item)}" for item in sources)
    else:
        lines.append("- Unknown")
    return "\n".join(lines).rstrip() + "\n"


def render_comparison_markdown(comparison: BuildComparison) -> str:
    """Render a deterministic structural comparison without combat claims."""

    lines = [
        "# WvW Thief Build Comparison",
        "",
        f"- Left build: {_text(comparison.left_build_id)}",
        f"- Right build: {_text(comparison.right_build_id)}",
    ]
    for heading, changes in (
        ("Additions", comparison.additions),
        ("Removals", comparison.removals),
        ("Replacements", comparison.replacements),
    ):
        lines.extend(["", f"## {heading}", ""])
        if not changes:
            lines.append("- None")
            continue
        for change in changes:
            value = change.to_dict()
            rendered = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ": ")
            )
            lines.append(f"- `{_text(rendered)}`")
    return "\n".join(lines).rstrip() + "\n"


def _equipment_rows(build: BuildRecord) -> list[str]:
    rows: list[str] = []
    weapons = {
        value.get("slot"): value
        for value in build.weapons
        if isinstance(value.get("slot"), str)
    }
    for slot in _WEAPON_SLOTS:
        weapon = weapons.get(slot)
        rows.append(
            _equipment_row(
                f"Weapon: {slot}",
                _weapon_value(weapon) if weapon is not None else "Unknown",
            )
        )
    unassigned = [
        value
        for value in build.weapons
        if not isinstance(value.get("slot"), str)
    ]
    for position, weapon in enumerate(unassigned, start=1):
        rows.append(
            _equipment_row(
                f"Weapon: unassigned {position}",
                _weapon_value(weapon),
            )
        )
    for slot in _ARMOR_SLOTS:
        rows.append(
            _equipment_row(
                f"Armor: {slot}",
                _component(build.armor.get(slot)),
            )
        )
    for slot in _TRINKET_SLOTS:
        rows.append(
            _equipment_row(
                f"Trinket: {slot}",
                _component(build.trinkets.get(slot)),
            )
        )
    for position in range(6):
        rune = build.runes[position] if position < len(build.runes) else None
        rows.append(_equipment_row(f"Rune: {position + 1}", _component(rune)))
    rows.append(_equipment_row("Relic", _component(build.relic)))
    if build.infusions:
        for position, infusion in enumerate(build.infusions, start=1):
            rows.append(
                _equipment_row(
                    f"Infusion: {position}",
                    _component(infusion),
                )
            )
    else:
        rows.append(_equipment_row("Infusions", "Unknown"))
    rows.append(
        _equipment_row(
            "Consumable: food",
            _component(build.consumables.get("food")),
        )
    )
    rows.append(
        _equipment_row(
            "Consumable: utility", _component(build.consumables.get("utility"))
        )
    )
    return rows


def _equipment_row(slot: str, value: str) -> str:
    return f"| {_text(slot)} | {_text(value)} |"


def _weapon_value(weapon: Mapping[str, Any]) -> str:
    parts = []
    for label, field in (("type", "type"), ("item", "item")):
        value = _component(weapon.get(field))
        if value != "Unknown":
            parts.append(f"{label}: {value}")
    return "; ".join(parts) if parts else "Unknown"


def _component(value: Any) -> str:
    if not isinstance(value, ComponentRef):
        return "Unknown"
    if value.name and value.id is not None:
        return f"{value.name} ({value.id})"
    if value.name:
        return value.name
    if value.id is not None:
        return str(value.id)
    return "Unknown"


def _conclusion_lines(conclusions: Iterable[Any]) -> list[str]:
    values = list(conclusions)
    if not values:
        return ["- None"]
    return [
        f"- {_text(item.claim)} (rule: {_text(item.rule_id)})" for item in values
    ]


def _risk_lines(audit: BuildAudit) -> list[str]:
    risks = list(audit.warnings)
    risks.extend(
        (
            f"{item.impact}: {item.component_kind}:{item.component_id} "
            f"changed {item.effective_at} ({item.change})"
        )
        for item in audit.affected_components
    )
    risks.extend(
        f"unknown {item.component_kind}:{item.component_id} at {item.field}"
        for item in audit.unknown_components
    )
    risks.extend(
        f"removed {item.component_kind}:{item.component_id} at {item.field}"
        for item in audit.removed_components
    )
    return [f"- {_text(item)}" for item in risks] if risks else ["- None"]


def _all_evidence(analysis: BuildAnalysis) -> tuple[EvidenceReference, ...]:
    values = {
        item
        for dimension in analysis.dimensions.values()
        for item in dimension.evidence
    }
    values.update(
        item
        for conclusion in (*analysis.strengths, *analysis.weaknesses)
        for item in conclusion.evidence
    )
    values.update(
        item
        for improvement in analysis.improvements
        for item in improvement.evidence
    )
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.component_kind,
                0 if isinstance(item.component_id, int) else 1,
                item.component_id,
                item.field,
            ),
        )
    )


def _source(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "Unknown"
    name = value.get("source")
    detail = value.get("url", value.get("value"))
    if name is None and detail is None:
        return "Unknown"
    if detail is None:
        return _display(name)
    if name is None:
        return _display(detail)
    return f"{_display(name)}: {_display(detail)}"


def _selector(value: Any) -> str:
    parts = [
        getattr(value, "component_kind", None),
        getattr(value, "component_id", None),
        getattr(value, "field", None),
    ]
    return ":".join(_display(item) for item in parts if item is not None)


def _joined(values: Iterable[Any]) -> str:
    rendered = ", ".join(_text(item) for item in values)
    return rendered or "Unknown"


def _display(value: Any) -> str:
    return "Unknown" if value is None or value == "" else _text(value)


def _text(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
