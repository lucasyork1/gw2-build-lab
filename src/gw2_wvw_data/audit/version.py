"""Patch event types used by version audits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping


@dataclass(frozen=True)
class PatchEvent:
    """One official post-source change to a stable component."""

    component_kind: str
    component_id: int | str
    effective_at: str
    change: str
    impact: str = "possibly_affected"

    def __post_init__(self) -> None:
        if not self.component_kind:
            raise ValueError("patch event component_kind is required")
        if not isinstance(self.component_id, (int, str)) or isinstance(
            self.component_id, bool
        ):
            raise ValueError("patch event component_id is invalid")
        try:
            date.fromisoformat(self.effective_at)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "patch event effective_at must be YYYY-MM-DD"
            ) from error
        if not self.change:
            raise ValueError("patch event change is required")
        if self.impact not in {"possibly_affected", "stale"}:
            raise ValueError(
                "patch event impact must be possibly_affected or stale"
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PatchEvent:
        return cls(
            component_kind=value["component_kind"],
            component_id=value["component_id"],
            effective_at=value["effective_at"],
            change=value["change"],
            impact=value.get("impact", "possibly_affected"),
        )


@dataclass(frozen=True)
class AffectedComponent:
    """A build component changed by a later patch event."""

    component_kind: str
    component_id: int | str
    effective_at: str
    change: str
    impact: str

    @classmethod
    def from_event(cls, event: PatchEvent) -> AffectedComponent:
        return cls(
            component_kind=event.component_kind,
            component_id=event.component_id,
            effective_at=event.effective_at,
            change=event.change,
            impact=event.impact,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_kind": self.component_kind,
            "component_id": self.component_id,
            "effective_at": self.effective_at,
            "change": self.change,
            "impact": self.impact,
        }
