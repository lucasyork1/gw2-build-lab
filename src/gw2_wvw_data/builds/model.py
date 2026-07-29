"""Immutable canonical representation for a WvW Thief build."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping

from gw2_wvw_data.contracts import schema_errors


CONFIDENCE_VALUES = frozenset({"exact", "mapped", "publisher_claimed", "unknown"})


@dataclass(frozen=True)
class ComponentRef:
    id: int | str
    name: str | None
    source: str
    confidence: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ComponentRef:
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "source": self.source, "confidence": self.confidence}


@dataclass(frozen=True)
class FieldProvenance:
    value: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FieldProvenance:
        return cls(_freeze(value))

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self.value)


@dataclass(frozen=True)
class SourceRecord:
    value: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SourceRecord:
        return cls(_freeze(value))

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self.value)


def _freeze(value: Any) -> Any:
    if isinstance(value, ComponentRef):
        return value
    if isinstance(value, Mapping):
        if set(value) == {"id", "name", "source", "confidence"}:
            return ComponentRef.from_dict(value)
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, ComponentRef):
        return value.to_dict()
    if isinstance(value, FieldProvenance | SourceRecord):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class BuildRecord:
    schema_version: int
    build_id: str
    profession: str
    mode: str
    context: tuple[str, ...]
    specializations: tuple[ComponentRef, ...]
    traits: tuple[ComponentRef, ...]
    skills: Mapping[str, ComponentRef | tuple[ComponentRef | None, ...] | None]
    weapons: tuple[Mapping[str, Any], ...]
    armor: Mapping[str, ComponentRef | None]
    trinkets: Mapping[str, ComponentRef | None]
    runes: tuple[ComponentRef | None, ...]
    relic: ComponentRef | None
    infusions: tuple[ComponentRef | None, ...]
    consumables: Mapping[str, ComponentRef | None]
    assumptions: Mapping[str, Any]
    provenance: Mapping[str, Any]
    version_audit: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BuildRecord:
        errors = schema_errors(value, "build.schema.json")
        if value.get("profession") != "Thief":
            raise ValueError("profession must be Thief")
        if value.get("mode") != "wvw":
            raise ValueError("mode must be wvw")
        if errors:
            raise ValueError(f"build schema invalid: {errors[0]}")
        return cls(
            schema_version=value["schema_version"], build_id=value["build_id"],
            profession=value["profession"], mode=value["mode"], context=tuple(value["context"]),
            specializations=tuple(ComponentRef.from_dict(item) for item in value["specializations"]),
            traits=tuple(ComponentRef.from_dict(item) for item in value["traits"]),
            skills=_freeze(value["skills"]), weapons=tuple(_freeze(item) for item in value["weapons"]),
            armor=_freeze(value["armor"]), trinkets=_freeze(value["trinkets"]),
            runes=tuple(_freeze(value["runes"])), relic=_freeze(value["relic"]),
            infusions=tuple(_freeze(value["infusions"])), consumables=_freeze(value["consumables"]),
            assumptions=_freeze(value["assumptions"]), provenance=_freeze(value["provenance"]),
            version_audit=_freeze(value["version_audit"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return _thaw({
            "schema_version": self.schema_version, "build_id": self.build_id,
            "profession": self.profession, "mode": self.mode, "context": self.context,
            "specializations": self.specializations, "traits": self.traits, "skills": self.skills,
            "weapons": self.weapons, "armor": self.armor, "trinkets": self.trinkets,
            "runes": self.runes, "relic": self.relic, "infusions": self.infusions,
            "consumables": self.consumables, "assumptions": self.assumptions,
            "provenance": self.provenance, "version_audit": self.version_audit,
        })

    def with_updates(self, **changes: Any) -> BuildRecord:
        return replace(self, **changes)
