"""Detached milestone records and tri-state partial updates."""

from typing import Any, Mapping, TypedDict


class MilestoneRecord(TypedDict):
    milestone_id: str
    card_id: str
    start_at: int
    end_at: int | None
    all_day: bool
    kind: str | None
    description: str | None
    created_at: int
    updated_at: int


class ProjectMilestoneRecord(MilestoneRecord):
    project_id: str
    card_title: str | None


class MilestoneUpdate(TypedDict, total=False):
    """Absent means unchanged; nullable fields accept None to clear."""

    start_at: int
    end_at: int | None
    all_day: bool
    kind: str | None
    description: str | None


MILESTONE_RECORD_FIELDS: tuple[str, ...] = (
    "milestone_id", "card_id", "start_at", "end_at", "all_day",
    "kind", "description", "created_at", "updated_at",
)
PROJECT_MILESTONE_RECORD_FIELDS: tuple[str, ...] = (
    "project_id", *MILESTONE_RECORD_FIELDS, "card_title",
)


def _milestone_record_from_native(item: Mapping[str, Any]) -> MilestoneRecord:
    return {
        "milestone_id": str(item["milestone_id"]), "card_id": str(item["card_id"]),
        "start_at": int(item["start_at"]),
        "end_at": None if item["end_at"] is None else int(item["end_at"]),
        "all_day": bool(item["all_day"]),
        "kind": None if item["kind"] is None else str(item["kind"]),
        "description": None if item["description"] is None else str(item["description"]),
        "created_at": int(item["created_at"]), "updated_at": int(item["updated_at"]),
    }


def _validate_update(changes: MilestoneUpdate) -> None:
    for field, value in changes.items():
        if field not in {"start_at", "end_at", "all_day", "kind", "description"}:
            raise ValueError(f"Unknown milestone update field: {field}")
        if value is None:
            if field in {"start_at", "all_day"}:
                raise ValueError(f"{field} must not be None")
            continue
        if field in {"start_at", "end_at"}:
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field} must be an integer Unix second")
            if not -(2**63) <= value < 2**63:
                raise OverflowError(f"{field} is outside signed 64-bit range")
        elif field == "all_day":
            if not isinstance(value, bool):
                raise TypeError("all_day must be bool")
        elif not isinstance(value, str):
            raise TypeError(f"{field} must be str or None")
