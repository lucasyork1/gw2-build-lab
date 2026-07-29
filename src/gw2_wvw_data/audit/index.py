"""Indexes over one normalized dataset, built once per analysis."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class EntityMetadata:
    """Version and source metadata retained beside an indexed entity."""

    game_build_id: int | None
    effective_patch: str | None
    source_refs: tuple[str, ...]
    verification_status: str | None


@dataclass(frozen=True)
class DatasetIndex:
    """Read-only lookup tables derived from a normalized Thief dataset."""

    entities: Mapping[tuple[str, int | str], Mapping[str, Any]]
    specialization_trait_tiers: Mapping[
        int, Mapping[int, frozenset[int]]
    ]
    profession_weapons: Mapping[str, Mapping[str, Any]]
    skill_palette: Mapping[int, int]
    entity_metadata: Mapping[tuple[str, int | str], EntityMetadata]
    game_build_id: int | None
    dataset_build_matches: bool

    @classmethod
    def from_dataset(cls, dataset: Mapping[str, Any]) -> DatasetIndex:
        """Index entities and legality metadata without mutating the dataset."""

        manifest = dataset.get("manifest", {})
        game_build_id = (
            manifest.get("game_build_id")
            if isinstance(manifest, Mapping)
            and type(manifest.get("game_build_id")) is int
            else None
        )
        entities: dict[
            tuple[str, int | str], Mapping[str, Any]
        ] = {}
        metadata: dict[
            tuple[str, int | str], EntityMetadata
        ] = {}
        records: list[Mapping[str, Any]] = []
        profession = dataset.get("profession")
        if isinstance(profession, Mapping):
            records.append(profession)
        for section in (
            "specializations",
            "traits",
            "skills",
            "itemstats",
            "equipment",
            "upgrades",
            "consumables",
        ):
            value = dataset.get(section, ())
            if isinstance(value, (list, tuple)):
                records.extend(
                    item for item in value if isinstance(item, Mapping)
                )

        build_matches = game_build_id is not None
        for record in records:
            kind = record.get("kind")
            identifier = record.get("id")
            if (
                not isinstance(kind, str)
                or not isinstance(identifier, (int, str))
                or isinstance(identifier, bool)
            ):
                continue
            key = (kind, identifier)
            entities[key] = record
            record_build = record.get("game_build_id")
            if record_build != game_build_id:
                build_matches = False
            source_refs = record.get("source_refs", ())
            metadata[key] = EntityMetadata(
                game_build_id=(
                    record_build if type(record_build) is int else None
                ),
                effective_patch=(
                    record.get("effective_patch")
                    if isinstance(record.get("effective_patch"), str)
                    else None
                ),
                source_refs=tuple(
                    item for item in source_refs if isinstance(item, str)
                )
                if isinstance(source_refs, (list, tuple))
                else (),
                verification_status=(
                    record.get("verification_status")
                    if isinstance(record.get("verification_status"), str)
                    else None
                ),
            )

        trait_tiers: dict[int, dict[int, frozenset[int]]] = {}
        specializations = dataset.get("specializations", ())
        if isinstance(specializations, (list, tuple)):
            for record in specializations:
                if not isinstance(record, Mapping):
                    continue
                identifier = record.get("id")
                payload = record.get("payload", {})
                if type(identifier) is not int or not isinstance(
                    payload, Mapping
                ):
                    continue
                major_traits = payload.get("major_traits", ())
                if not isinstance(major_traits, (list, tuple)):
                    continue
                trait_tiers[identifier] = {
                    tier: frozenset(
                        item
                        for item in major_traits[
                            (tier - 1) * 3 : tier * 3
                        ]
                        if type(item) is int
                    )
                    for tier in (1, 2, 3)
                }

        profession_payload = (
            profession.get("payload", {})
            if isinstance(profession, Mapping)
            else {}
        )
        raw_weapons = (
            profession_payload.get("weapons", {})
            if isinstance(profession_payload, Mapping)
            else {}
        )
        weapons: dict[str, Mapping[str, Any]] = {}
        if isinstance(raw_weapons, Mapping):
            for name, value in raw_weapons.items():
                if not isinstance(name, str) or not isinstance(value, Mapping):
                    continue
                flags = value.get("flags", ())
                weapons[name] = MappingProxyType(
                    {
                        **value,
                        "flags": tuple(flags)
                        if isinstance(flags, (list, tuple))
                        else (),
                    }
                )

        raw_palette = (
            profession_payload.get("skills_by_palette", ())
            if isinstance(profession_payload, Mapping)
            else ()
        )
        palette: dict[int, int] = {}
        if isinstance(raw_palette, (list, tuple)):
            for pair in raw_palette:
                if (
                    isinstance(pair, (list, tuple))
                    and len(pair) == 2
                    and type(pair[0]) is int
                    and type(pair[1]) is int
                ):
                    palette[pair[0]] = pair[1]

        return cls(
            entities=MappingProxyType(entities),
            specialization_trait_tiers=MappingProxyType(
                {
                    key: MappingProxyType(value)
                    for key, value in trait_tiers.items()
                }
            ),
            profession_weapons=MappingProxyType(weapons),
            skill_palette=MappingProxyType(palette),
            entity_metadata=MappingProxyType(metadata),
            game_build_id=game_build_id,
            dataset_build_matches=build_matches,
        )

    def entity(
        self, kind: str, identifier: int | str
    ) -> Mapping[str, Any] | None:
        """Return one normalized entity by its stable kind and ID."""

        return self.entities.get((kind, identifier))
