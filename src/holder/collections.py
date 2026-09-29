"""Live collection facades which produce detached Holder models and records."""

from __future__ import annotations

import builtins
from typing import Any, Literal, Mapping, overload

from . import _native
from .data.card import (
    Card,
    CardMetadataRecord,
    CompleteCardRecord,
    _complete_record_from_native,
    _metadata_record_from_native,
)
from .data.project import Project, ProjectRecord


_COMPLETE_CARD_PAGE_SIZE = 256


class ProjectCollection:
    """Read projects from a live context and return detached snapshots."""

    __slots__ = ("_context",)

    def __init__(self, context: _native.Context) -> None:
        self._context = context

    def list(self) -> builtins.list[Project]:
        return [Project._from_native(item) for item in self._context.list_projects()]

    def to_records(self) -> builtins.list[ProjectRecord]:
        return [project.to_record() for project in self.list()]


class CardCollection:
    """Read live cards from a context and return detached snapshots."""

    __slots__ = ("_context",)

    def __init__(self, context: _native.Context) -> None:
        self._context = context

    def _project_ids(self, project_id: str | None) -> builtins.list[str]:
        return (
            [project_id]
            if project_id is not None
            else [item["project_id"] for item in self._context.list_projects()]
        )

    def _complete_records(
        self, project_id: str | None
    ) -> builtins.list[CompleteCardRecord]:
        records: builtins.list[CompleteCardRecord] = []
        for current_project_id in self._project_ids(project_id):
            cursor: str | None = None
            while True:
                page: Mapping[str, Any] = self._context.list_complete_cards_page(
                    current_project_id, cursor, _COMPLETE_CARD_PAGE_SIZE
                )
                records.extend(
                    _complete_record_from_native(item) for item in page["cards"]
                )
                next_cursor = page["next_cursor"]
                if next_cursor is None:
                    break
                cursor = str(next_cursor)
        return records

    def list(self, project_id: str | None = None) -> builtins.list[Card]:
        return [
            Card._from_native(record, record["content"])
            for record in self._complete_records(project_id)
        ]

    @overload
    def to_records(
        self,
        project_id: str | None = None,
        *,
        include_content: Literal[False] = False,
    ) -> builtins.list[CardMetadataRecord]: ...

    @overload
    def to_records(
        self,
        project_id: str | None = None,
        *,
        include_content: Literal[True],
    ) -> builtins.list[CompleteCardRecord]: ...

    def to_records(
        self, project_id: str | None = None, *, include_content: bool = False
    ) -> builtins.list[CardMetadataRecord] | builtins.list[CompleteCardRecord]:
        if include_content:
            return self._complete_records(project_id)

        records: builtins.list[CardMetadataRecord] = []
        for current_project_id in self._project_ids(project_id):
            records.extend(
                _metadata_record_from_native(item)
                for item in self._context.list_cards(current_project_id)
            )
        return records
