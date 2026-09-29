"""Stable, detached dictionary contracts for Holder data."""

from __future__ import annotations

from typing import TypedDict


class ProjectRecord(TypedDict):
    """Serializable project fields returned by the public libholder API."""

    project_id: str
    name: str
    root_path: str
    privacy_mode: str
    id_scheme: str
    created_at: int
    updated_at: int
    git_remote_url: str | None
    git_provider: str | None
    project_key_id: str | None


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


PROJECT_RECORD_FIELDS: tuple[str, ...] = (
    "project_id",
    "name",
    "root_path",
    "privacy_mode",
    "id_scheme",
    "created_at",
    "updated_at",
    "git_remote_url",
    "git_provider",
    "project_key_id",
)

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
