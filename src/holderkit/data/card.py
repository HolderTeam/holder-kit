"""Live card interface and detached record contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Mapping, TypedDict, overload

if TYPE_CHECKING:
    from .project import Project
    from ..card_collections import CardTags, CardConnections, CardMilestones


class CardMetadataRecord(TypedDict):
    """Serializable live-card metadata without its body."""

    card_id: str
    project_id: str
    title: str
    rel_path: str
    parent_card_id: str | None
    sort_key: float
    created_at: int
    updated_at: int
    deleted_at: int | None


class CompleteCardRecord(CardMetadataRecord):
    """Serializable live-card metadata and its authoritative Markdown body."""

    content: str


CARD_METADATA_RECORD_FIELDS: tuple[str, ...] = (
    "card_id",
    "project_id",
    "title",
    "rel_path",
    "parent_card_id",
    "sort_key",
    "created_at",
    "updated_at",
    "deleted_at",
)

COMPLETE_CARD_RECORD_FIELDS: tuple[str, ...] = (
    "card_id",
    "project_id",
    "title",
    "content",
    "rel_path",
    "parent_card_id",
    "sort_key",
    "created_at",
    "updated_at",
    "deleted_at",
)

# Increment 2 called the complete-body contract CardRecord. Preserve that public
# spelling while giving metadata-only and complete exports distinct precise names.
CardRecord = CompleteCardRecord
CARD_RECORD_FIELDS = COMPLETE_CARD_RECORD_FIELDS


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _metadata_record_from_native(record: Mapping[str, Any]) -> CardMetadataRecord:
    return {
        "card_id": str(record["card_id"]),
        "project_id": str(record["project_id"]),
        "title": str(record["title"]),
        "rel_path": str(record["rel_path"]),
        "parent_card_id": _optional_string(record["parent_card_id"]),
        "sort_key": float(record["sort_key"]),
        "created_at": int(record["created_at"]),
        "updated_at": int(record["updated_at"]),
        "deleted_at": _optional_int(record["deleted_at"]),
    }


def _complete_record_from_native(record: Mapping[str, Any]) -> CompleteCardRecord:
    metadata = _metadata_record_from_native(record)
    return {
        "card_id": metadata["card_id"],
        "project_id": metadata["project_id"],
        "title": metadata["title"],
        "content": str(record["content"]),
        "rel_path": metadata["rel_path"],
        "parent_card_id": metadata["parent_card_id"],
        "sort_key": metadata["sort_key"],
        "created_at": metadata["created_at"],
        "updated_at": metadata["updated_at"],
        "deleted_at": metadata["deleted_at"],
    }


class Card:
    """A live card owned by a Project; export records before closing it.

    Identity and project remain available after close or purge. Descriptive
    properties read current state and require an open owning project.
    """

    __slots__ = ("_project", "_card_id")

    def __init__(self, project: Project, card_id: str) -> None:
        from .project import Project

        if not isinstance(project, Project):
            raise TypeError("project must be a Project")
        if not isinstance(card_id, str):
            raise TypeError("card_id must be a string")
        if not card_id:
            raise ValueError("card_id must not be empty")
        self._project = project
        self._card_id = card_id

    @classmethod
    def _from_native(cls, record: Mapping[str, Any], project: Project) -> Card:
        if record["project_id"] != project.project_id:
            raise ValueError("Card does not belong to this project")
        return cls(project, str(record["card_id"]))

    @property
    def project(self) -> Project:
        """The owning Project instance, also available after closing."""
        return self._project

    @property
    def card_id(self) -> str:
        return self._card_id

    @property
    def project_id(self) -> str:
        return self.project.project_id

    def _current(self) -> Mapping[str, Any]:
        return self.project._card_record(self.card_id)

    @property
    def title(self) -> str:
        return str(self._current()["title"])

    @property
    def content(self) -> str:
        record = self._current()
        return self._content(record)

    def _content(self, record: Mapping[str, Any]) -> str:
        if record["deleted_at"] is not None:
            raise ValueError("Card is in Trash; restore it before reading content")
        return self.project._live_context().get_card_content(self.card_id)

    @property
    def rel_path(self) -> str:
        return str(self._current()["rel_path"])

    @property
    def parent_card_id(self) -> str | None:
        return _optional_string(self._current()["parent_card_id"])

    @property
    def sort_key(self) -> float:
        return float(self._current()["sort_key"])

    @property
    def created_at(self) -> int:
        return int(self._current()["created_at"])

    @property
    def updated_at(self) -> int:
        return int(self._current()["updated_at"])

    @property
    def deleted_at(self) -> int | None:
        return _optional_int(self._current()["deleted_at"])

    @property
    def created_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.created_at, tz=timezone.utc)

    @property
    def updated_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.updated_at, tz=timezone.utc)

    @property
    def deleted_datetime(self) -> datetime | None:
        deleted_at = self.deleted_at
        return None if deleted_at is None else datetime.fromtimestamp(deleted_at, tz=timezone.utc)

    @property
    def tags(self) -> CardTags:
        from ..card_collections import CardTags

        return CardTags(self)

    @property
    def connections(self) -> CardConnections:
        from ..card_collections import CardConnections

        return CardConnections(self)

    @property
    def milestones(self) -> CardMilestones:
        from ..card_collections import CardMilestones

        return CardMilestones(self)

    def update(self, content: str, title: str | None = None) -> Card:
        """Save content and an optional title, returning a live Card."""
        return self.project.update_card(self.card_id, content, title)

    def delete(self, *, hard: bool = False) -> None:
        """Move to Trash, or permanently remove an already-trashed card with hard=True."""
        self.project.delete(self, hard=hard)

    def trash(self) -> None:
        """Move to Trash; equivalent to delete(). Live children are promoted by Core."""
        self.project.trash(self)

    def purge(self) -> None:
        """Permanently remove an already-trashed card; equivalent to delete(hard=True)."""
        self.project.purge(self)

    def restore(self) -> Card:
        """Restore this card alone and return a live Card with the same owner."""
        return self.project.restore(self)

    @overload
    def to_record(self, *, include_content: Literal[True] = True) -> CompleteCardRecord: ...

    @overload
    def to_record(self, *, include_content: Literal[False]) -> CardMetadataRecord: ...

    @overload
    def to_record(self, *, include_content: bool) -> CardMetadataRecord | CompleteCardRecord: ...

    def to_record(self, *, include_content: bool = True) -> CardMetadataRecord | CompleteCardRecord:
        """Copy current values into a detached record; bodies are included by default.

        Use include_content=False for metadata only, including cards in Trash.
        Separate metadata and body reads do not promise an atomic snapshot.
        """
        if not isinstance(include_content, bool):
            raise TypeError("include_content must be a bool")
        record = self._current()
        if include_content:
            return _complete_record_from_native({**record, "content": self._content(record)})
        return _metadata_record_from_native(record)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return (self.project._context is other.project._context and
                self.project_id == other.project_id and self.card_id == other.card_id)

    def __hash__(self) -> int:
        return hash((self.project._context, self.project_id, self.card_id))

    def __repr__(self) -> str:
        return f"Card(card_id={self.card_id!r}, project_id={self.project_id!r})"


__all__ = [
    "CARD_METADATA_RECORD_FIELDS",
    "CARD_RECORD_FIELDS",
    "COMPLETE_CARD_RECORD_FIELDS",
    "Card",
    "CardMetadataRecord",
    "CardRecord",
    "CompleteCardRecord",
]
