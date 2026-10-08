"""Live project interface and detached record contract."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, TypedDict

from .. import _native

if TYPE_CHECKING:
    import networkx as nx

    from ..dataframe import DataFrames
    from ..project_collections import (
        ProjectCards,
        ProjectConnections,
        ProjectMilestones,
        ProjectTags,
    )
    from .card import Card


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


def _project_record_from_native(record: Mapping[str, Any]) -> ProjectRecord:
    return {
        "project_id": str(record["project_id"]),
        "name": str(record["name"]),
        "root_path": str(record["root_path"]),
        "privacy_mode": str(record["privacy_mode"]),
        "id_scheme": str(record["id_scheme"]),
        "created_at": int(record["created_at"]),
        "updated_at": int(record["updated_at"]),
        "git_remote_url": _optional_string(record["git_remote_url"]),
        "git_provider": _optional_string(record["git_provider"]),
        "project_key_id": _optional_string(record["project_key_id"]),
    }


class Project:
    """Work with one Holder project; descriptive properties read current state.

    Managed projects own their context. Projects obtained from a Context borrow
    it: closing one such project does not close its siblings or the Context.
    Export to_record() to retain a detached snapshot after closing.
    """

    __slots__ = ("_context", "_project_id", "_owns_context", "_closed", "_path")

    def __init__(
        self,
        context: _native.Context,
        project_id: str,
        *,
        owns_context: bool = False,
        path: Path | None = None,
    ) -> None:
        self._context = context
        self._project_id = project_id
        self._owns_context = owns_context
        self._closed = False
        self._path = path

    @classmethod
    def _from_native(
        cls, record: Mapping[str, Any], context: _native.Context
    ) -> Project:
        return cls(context, str(record["project_id"]))

    @property
    def project_id(self) -> str:
        """Stable identity, also available after closing."""
        return self._project_id

    @property
    def closed(self) -> bool:
        return self._closed or self._context.closed

    def _live_context(self) -> _native.Context:
        if self.closed:
            raise RuntimeError("Holder project is closed")
        return self._context

    def _current(self) -> Mapping[str, Any]:
        for record in self._live_context().list_projects():
            if record["project_id"] == self._project_id:
                return record
        raise _native.HolderError("project not found: " + self._project_id)

    @property
    def name(self) -> str:
        return str(self._current()["name"])

    @property
    def root_path(self) -> str:
        return str(self._current()["root_path"])

    @property
    def privacy_mode(self) -> str:
        return str(self._current()["privacy_mode"])

    @property
    def id_scheme(self) -> str:
        return str(self._current()["id_scheme"])

    @property
    def created_at(self) -> int:
        return int(self._current()["created_at"])

    @property
    def updated_at(self) -> int:
        return int(self._current()["updated_at"])

    @property
    def git_remote_url(self) -> str | None:
        return _optional_string(self._current()["git_remote_url"])

    @property
    def git_provider(self) -> str | None:
        return _optional_string(self._current()["git_provider"])

    @property
    def project_key_id(self) -> str | None:
        return _optional_string(self._current()["project_key_id"])

    @property
    def path(self) -> Path:
        """Managed storage directory for reopen(); available after closing."""
        if self._path is None:
            raise ValueError("Project belongs to a Context, not managed storage")
        return self._path

    @property
    def revision(self) -> str:
        """Current Git HEAD, including commits made since opening."""
        from .._storage import _git

        return _git("-C", self.root_path, "rev-parse", "HEAD").decode("ascii").strip()

    @property
    def remote_url(self) -> str | None:
        """Current origin remote, if configured."""
        from .._storage import _git

        # Query all remote URLs so an absent origin is an ordinary empty result.
        for line in _git("-C", self.root_path, "remote", "-v").decode().splitlines():
            fields = line.split()
            if fields[0] == "origin" and fields[-1] == "(fetch)":
                return fields[1]
        return None

    @property
    def cards(self) -> ProjectCards:
        from ..project_collections import ProjectCards

        return ProjectCards(self)

    @property
    def connections(self) -> ProjectConnections:
        from ..project_collections import ProjectConnections

        return ProjectConnections(self)

    @property
    def tags(self) -> ProjectTags:
        from ..project_collections import ProjectTags

        return ProjectTags(self)

    @property
    def milestones(self) -> ProjectMilestones:
        from ..project_collections import ProjectMilestones

        return ProjectMilestones(self)

    def _require_card(self, card_id: str) -> None:
        if not any(
            card["card_id"] == card_id
            for card in self._live_context().list_cards(self.project_id)
        ):
            raise ValueError("Card does not belong to this project")

    def create_card(
        self,
        title: str,
        content: str = "",
        parent_card_id: str | None = None,
    ) -> Card:
        from .card import Card

        if parent_card_id is not None:
            self._require_card(parent_card_id)
        record = self._live_context().create_card(
            self.project_id, title, content, parent_card_id
        )
        return Card._from_native(record, content)

    def list_cards(self) -> list[Card]:
        return self.cards.list()

    def get_card_content(self, card_id: str) -> str:
        self._require_card(card_id)
        return self._live_context().get_card_content(card_id)

    def update_card(self, card_id: str, content: str, title: str | None = None) -> Card:
        from .card import Card

        self._require_card(card_id)
        record = self._live_context().update_card(card_id, content, title)
        return Card._from_native(record, content)

    def to_dataframes(self, *, include_content: bool = False) -> DataFrames:
        from .. import Context

        return Context._from_native(self._live_context()).to_dataframes(
            self.project_id,
            include_content=include_content,
        )

    def to_networkx(self, *, include_content: bool = False) -> nx.MultiDiGraph[str]:
        from .. import Context

        return Context._from_native(self._live_context()).to_networkx(
            self.project_id,
            include_content=include_content,
        )

    def close(self) -> None:
        if self._owns_context:
            self._context.close()
        self._closed = True

    def __enter__(self) -> Project:
        self._live_context()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def created_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.created_at, tz=timezone.utc)

    @property
    def updated_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.updated_at, tz=timezone.utc)

    def to_record(self) -> ProjectRecord:
        """Read one current project record and detach it from the live context."""
        record = self._current()
        return _project_record_from_native(record)


__all__ = ["PROJECT_RECORD_FIELDS", "Project", "ProjectRecord"]
