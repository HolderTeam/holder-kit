"""Holder Kit: a small public interface to embedded libholder."""

from __future__ import annotations

import os
import sys
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import networkx as nx

# Keep the directory handle alive while the extension and its bundled Windows
# dependencies are loaded. Wheels do not require a caller-managed PATH.
_dll_directory: object = None
if sys.platform == "win32" and (Path(__file__).parent / ".libs").is_dir():
    _dll_directory = os.add_dll_directory(str(Path(__file__).parent / ".libs"))

from . import _native
from .collections import CardCollection, ConnectionCollection, ProjectCollection, TagCollection, MilestoneCollection
from .graph import records_to_networkx
from .dataframe import DataFrames, _require_pandas, records_to_dataframe
from .data import (
    MILESTONE_RECORD_FIELDS, PROJECT_MILESTONE_RECORD_FIELDS,
    MilestoneRecord, ProjectMilestoneRecord, MilestoneUpdate,
    TAG_RECORD_FIELDS, ProjectTagRecord, TaggedCardRecord, TagRecord, TagAddResult, TagRemoveResult,
    CARD_METADATA_RECORD_FIELDS,
    CARD_RECORD_FIELDS,
    COMPLETE_CARD_RECORD_FIELDS,
    PROJECT_RECORD_FIELDS,
    CONNECTION_RECORD_FIELDS,
    ConnectionRecord,
    Card,
    CardMetadataRecord,
    CardRecord,
    CompleteCardRecord,
    Project,
    ProjectRecord,
)

HolderError = _native.HolderError


def _schema_sql() -> str:
    return files(__package__).joinpath("_schema.sql").read_text(encoding="utf-8")


class Context:
    """An embedded Holder context rooted in an isolated data directory."""

    __slots__ = ("_context",)

    def __init__(self, data_dir: os.PathLike[str] | str) -> None:
        self._context = _native.Context(os.fspath(data_dir), _schema_sql())

    @property
    def closed(self) -> bool:
        return self._context.closed

    def close(self) -> None:
        self._context.close()

    @property
    def projects(self) -> ProjectCollection:
        return ProjectCollection(self._context)

    @property
    def cards(self) -> CardCollection:
        return CardCollection(self._context)

    @property
    def connections(self) -> ConnectionCollection:
        return ConnectionCollection(self._context)

    @property
    def tags(self) -> TagCollection:
        return TagCollection(self._context)

    @property
    def milestones(self) -> MilestoneCollection:
        return MilestoneCollection(self._context)

    def to_dataframes(
        self, project_id: str | None = None, *, include_content: bool = False,
    ) -> DataFrames:
        """Export five detached entity tables, without atomicity.

        Project selection applies to source cards; referenced targets can fall
        outside the selected tables. Unknown project IDs yield empty tables.
        """

        _require_pandas()
        projects = self.projects.to_records()
        if project_id is not None:
            projects = [record for record in projects if record["project_id"] == project_id]
        cards: list[CardMetadataRecord] = []
        for project in projects:
            if include_content:
                cards.extend(self.cards.to_records(project["project_id"], include_content=True))
            else:
                cards.extend(self.cards.to_records(project["project_id"]))
        connections = self.connections._records_from_cards(cards)
        card_fields = COMPLETE_CARD_RECORD_FIELDS if include_content else CARD_METADATA_RECORD_FIELDS
        return {
            "projects": records_to_dataframe(projects, PROJECT_RECORD_FIELDS),
            "cards": records_to_dataframe(cards, card_fields),
            "connections": records_to_dataframe(connections, CONNECTION_RECORD_FIELDS),
            "tags": records_to_dataframe(self.tags._records_from_cards(cards), TAG_RECORD_FIELDS),
            "milestones": records_to_dataframe(
                self.milestones._records_from_cards(cards), PROJECT_MILESTONE_RECORD_FIELDS,
            ),
        }

    def to_networkx(
        self, project_id: str | None = None, *, include_content: bool = False,
    ) -> nx.MultiDiGraph[str]:
        """Export explicit card connections and all selected live cards."""

        cards = (
            self.cards.to_records(project_id, include_content=True)
            if include_content else self.cards.to_records(project_id)
        )
        return records_to_networkx(cards, self.connections._records_from_cards(cards))

    def create_project(self, name: str) -> Project:
        return Project._from_native(self._context.create_project(name))

    def list_projects(self) -> list[Project]:
        return self.projects.list()

    def create_card(
        self,
        project_id: str,
        title: str,
        content: str = "",
        parent_card_id: str | None = None,
    ) -> Card:
        metadata = self._context.create_card(
            project_id, title, content, parent_card_id
        )
        return Card._from_native(metadata, content)

    def list_cards(self, project_id: str) -> list[Card]:
        return self.cards.list(project_id)

    def get_card_content(self, card_id: str) -> str:
        return self._context.get_card_content(card_id)

    def update_card(
        self, card_id: str, content: str, title: str | None = None
    ) -> Card:
        metadata = self._context.update_card(card_id, content, title)
        return Card._from_native(metadata, content)

    def __enter__(self) -> Context:
        if self.closed:
            raise RuntimeError("Holder context is closed")
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def open(data_dir: os.PathLike[str] | str) -> Context:
    """Open an embedded Holder context for use directly or as a context manager."""

    return Context(data_dir)


__all__ = [
    "MILESTONE_RECORD_FIELDS", "PROJECT_MILESTONE_RECORD_FIELDS", "MilestoneCollection",
    "MilestoneRecord", "ProjectMilestoneRecord", "MilestoneUpdate",
    "TAG_RECORD_FIELDS", "TagCollection", "ProjectTagRecord", "TaggedCardRecord",
    "TagRecord", "TagAddResult", "TagRemoveResult",
    "CONNECTION_RECORD_FIELDS",
    "ConnectionCollection",
    "ConnectionRecord",
    "CARD_METADATA_RECORD_FIELDS",
    "CARD_RECORD_FIELDS",
    "COMPLETE_CARD_RECORD_FIELDS",
    "PROJECT_RECORD_FIELDS",
    "Card",
    "CardCollection",
    "CardMetadataRecord",
    "CardRecord",
    "CompleteCardRecord",
    "Context",
    "DataFrames",
    "HolderError",
    "Project",
    "ProjectCollection",
    "ProjectRecord",
    "open",
]
