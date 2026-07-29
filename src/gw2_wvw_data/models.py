"""Shared records used by the data pipeline."""

from dataclasses import dataclass
from enum import StrEnum


class VerificationStatus(StrEnum):
    """How a record was verified."""

    UNVERIFIED = "unverified"
    AUTOMATED = "automated"
    HUMAN_VERIFIED = "human_verified"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class SourceRef:
    """A traceable external source."""

    source_type: str
    url: str
    fetched_at: str
