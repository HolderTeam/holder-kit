"""Detached card model and record contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, TypedDict


class CardRecord(TypedDict):
    """Serializable card metadata plus its separately retrieved body."""

    card_id: str
    project_id: str
    title: str
    content: str
    rel_path: str
    parent_card_id: str | None
    sort_key: float
    created_at: int
    updated_at: int
    deleted_at: int | None


CARD_RECORD_FIELDS: tuple[str, ...] = (
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


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


@dataclass(frozen=True, slots=True)
class Card:
    """A detached card snapshot including its Markdown body."""

    card_id: str
    project_id: str
    title: str
    content: str
    rel_path: str
    parent_card_id: str | None
    sort_key: float
    created_at: int
    updated_at: int
    deleted_at: int | None

    @classmethod
    def _from_native(cls, record: Mapping[str, Any], content: str) -> Card:
        return cls(
            card_id=str(record["card_id"]),
            project_id=str(record["project_id"]),
            title=str(record["title"]),
            content=content,
            rel_path=str(record["rel_path"]),
            parent_card_id=_optional_string(record["parent_card_id"]),
            sort_key=float(record["sort_key"]),
            created_at=int(record["created_at"]),
            updated_at=int(record["updated_at"]),
            deleted_at=_optional_int(record["deleted_at"]),
        )

    @property
    def created_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.created_at, tz=timezone.utc)

    @property
    def updated_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.updated_at, tz=timezone.utc)

    @property
    def deleted_datetime(self) -> datetime | None:
        if self.deleted_at is None:
            return None
        return datetime.fromtimestamp(self.deleted_at, tz=timezone.utc)

    def to_record(self) -> CardRecord:
        return {
            "card_id": self.card_id,
            "project_id": self.project_id,
            "title": self.title,
            "content": self.content,
            "rel_path": self.rel_path,
            "parent_card_id": self.parent_card_id,
            "sort_key": self.sort_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }


__all__ = ["CARD_RECORD_FIELDS", "Card", "CardRecord"]
