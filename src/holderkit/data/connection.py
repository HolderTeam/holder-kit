"""Detached explicit outgoing connection record contract."""

from typing import TypedDict


class ConnectionRecord(TypedDict):
    """A directed connection owned by its source card's project."""

    project_id: str
    from_card_id: str
    to_card_id: str
    to_type: str
    kind: str
    label: str | None
    created_at: int
    to_title: str | None


CONNECTION_RECORD_FIELDS: tuple[str, ...] = (
    "project_id",
    "from_card_id",
    "to_card_id",
    "to_type",
    "kind",
    "label",
    "created_at",
    "to_title",
)
