"""Small public interface to embedded libholder."""

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
from .collections import CardCollection, ConnectionCollection, ProjectCollection
from .graph import records_to_networkx
from .data import (
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
    "HolderError",
    "Project",
    "ProjectCollection",
    "ProjectRecord",
    "open",
]
