"""Detached project model and record contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, TypedDict


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


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


@dataclass(frozen=True, slots=True)
class Project:
    """A detached snapshot of one Holder project."""

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

    @classmethod
    def _from_native(cls, record: Mapping[str, Any]) -> Project:
        return cls(
            project_id=str(record["project_id"]),
            name=str(record["name"]),
            root_path=str(record["root_path"]),
            privacy_mode=str(record["privacy_mode"]),
            id_scheme=str(record["id_scheme"]),
            created_at=int(record["created_at"]),
            updated_at=int(record["updated_at"]),
            git_remote_url=_optional_string(record["git_remote_url"]),
            git_provider=_optional_string(record["git_provider"]),
            project_key_id=_optional_string(record["project_key_id"]),
        )

    @property
    def created_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.created_at, tz=timezone.utc)

    @property
    def updated_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.updated_at, tz=timezone.utc)

    def to_record(self) -> ProjectRecord:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "root_path": self.root_path,
            "privacy_mode": self.privacy_mode,
            "id_scheme": self.id_scheme,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "git_remote_url": self.git_remote_url,
            "git_provider": self.git_provider,
            "project_key_id": self.project_key_id,
        }


__all__ = ["PROJECT_RECORD_FIELDS", "Project", "ProjectRecord"]
