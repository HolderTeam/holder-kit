"""Live collection facades which produce detached Holder models and records."""

from __future__ import annotations

import builtins
import json
from typing import TYPE_CHECKING, Any, Iterable, Literal, Mapping, overload

from . import _native
from .data.card import (
    CARD_METADATA_RECORD_FIELDS,
    COMPLETE_CARD_RECORD_FIELDS,
    Card,
    CardMetadataRecord,
    CompleteCardRecord,
    _complete_record_from_native,
    _metadata_record_from_native,
)
from .data.project import PROJECT_RECORD_FIELDS, Project, ProjectRecord
from .data.connection import CONNECTION_RECORD_FIELDS, ConnectionRecord
from .data.tag import (
    TAG_RECORD_FIELDS, ProjectTagRecord, TaggedCardRecord, TagRecord,
    TagAddResult, TagRemoveResult,
)
from .dataframe import records_to_dataframe
from .data.milestone import (
    PROJECT_MILESTONE_RECORD_FIELDS, MilestoneRecord, ProjectMilestoneRecord,
    MilestoneUpdate, _milestone_record_from_native, _validate_update,
)

if TYPE_CHECKING:
    import pandas as pd


_COMPLETE_CARD_PAGE_SIZE = 256


class MilestoneCollection:
    """Core-owned milestone operations and detached calendar records."""

    __slots__ = ("_context",)

    def __init__(self, context: _native.Context) -> None:
        self._context = context

    def list(self, card_id: str) -> builtins.list[MilestoneRecord]:
        return [_milestone_record_from_native(item) for item in self._context.list_milestones(card_id)]

    def add(
        self, card_id: str, start_at: int, *, end_at: int | None = None,
        all_day: bool = False, kind: str | None = None, description: str | None = None,
    ) -> builtins.list[MilestoneRecord]:
        """Return the card's updated full milestone list, not just the new row."""

        return [_milestone_record_from_native(item) for item in self._context.add_milestone(
            card_id, start_at, end_at, all_day, kind, description,
        )]

    def update(
        self, project_id: str, card_id: str, milestone_id: str, changes: MilestoneUpdate,
    ) -> MilestoneRecord:
        _validate_update(changes)
        return _milestone_record_from_native(self._context.update_milestone(
            project_id, card_id, milestone_id, json.dumps(changes),
        ))

    def remove(self, card_id: str, milestone_id: str) -> None:
        """Absent IDs or IDs belonging to another card are no-ops."""

        self._context.remove_milestone(card_id, milestone_id)

    def in_range(
        self, project_id: str, from_at: int, to_at: int,
    ) -> builtins.list[ProjectMilestoneRecord]:
        """Select start times in [from_at, to_at], not overlapping intervals."""

        return [{
            "project_id": project_id, **_milestone_record_from_native(item),
            "card_title": None if item["card_title"] is None else str(item["card_title"]),
        } for item in self._context.milestones_in_range(project_id, from_at, to_at)]

    def to_records(self, project_id: str | None = None) -> builtins.list[ProjectMilestoneRecord]:
        return self._records_from_cards(CardCollection(self._context).to_records(project_id))

    def _records_from_cards(
        self, cards: Iterable[CardMetadataRecord],
    ) -> builtins.list[ProjectMilestoneRecord]:
        return [{
            "project_id": card["project_id"], **milestone, "card_title": card["title"],
        } for card in cards for milestone in self.list(card["card_id"])]

    def to_dataframe(self, project_id: str | None = None) -> pd.DataFrame:
        return records_to_dataframe(self.to_records(project_id), PROJECT_MILESTONE_RECORD_FIELDS)


class TagCollection:
    """Core-extracted tags and explicit semantic mutations, not body parsing."""

    __slots__ = ("_context",)

    def __init__(self, context: _native.Context) -> None:
        self._context = context

    def list(self, card_id: str) -> builtins.list[str]:
        return self._context.list_tags(card_id)

    def list_editable(self, card_id: str) -> builtins.list[str]:
        return self._context.list_editable_tags(card_id)

    def add(self, card_id: str, tag: str) -> TagAddResult:
        return TagAddResult(self._context.add_tag(card_id, tag))

    def remove(self, card_id: str, tag: str) -> TagRemoveResult:
        return TagRemoveResult(self._context.remove_tag(card_id, tag))

    def project_counts(self, project_id: str) -> builtins.list[ProjectTagRecord]:
        """Return core's live-card counts, most-used first, then tag name."""

        return [
            {"project_id": project_id, "tag": str(item["tag"]), "count": int(item["count"])}
            for item in self._context.list_project_tags(project_id)
        ]

    def cards_with_tag(self, project_id: str, tag: str) -> builtins.list[TaggedCardRecord]:
        """Return detached live-card IDs/titles using core's case-insensitive search."""

        return [
            {"card_id": str(item["card_id"]), "title": str(item["title"])}
            for item in self._context.cards_with_tag(project_id, tag)
        ]

    def to_records(self, project_id: str | None = None) -> builtins.list[TagRecord]:
        return self._records_from_cards(CardCollection(self._context).to_records(project_id))

    def _records_from_cards(
        self, cards: Iterable[CardMetadataRecord],
    ) -> builtins.list[TagRecord]:
        records: builtins.list[TagRecord] = []
        for card in cards:
            tags = self.list(card["card_id"])
            if not tags:
                continue
            editable = set(self.list_editable(card["card_id"]))
            records.extend({
                "project_id": card["project_id"], "card_id": card["card_id"],
                "tag": tag, "editable": tag in editable,
            } for tag in tags)
        return records

    def to_dataframe(self, project_id: str | None = None) -> pd.DataFrame:
        return records_to_dataframe(self.to_records(project_id), TAG_RECORD_FIELDS)


class ConnectionCollection:
    """Explicit outgoing connections of live cards, read through core."""

    __slots__ = ("_context",)

    def __init__(self, context: _native.Context) -> None:
        self._context = context

    def add(
        self, from_card_id: str, to_card_id: str, kind: str,
        label: str | None = None,
    ) -> None:
        """Add or update a connection using core's existing upsert semantics."""

        self._context.add_link(from_card_id, to_card_id, kind, label)

    def remove(self, from_card_id: str, to_card_id: str, kind: str) -> None:
        """Remove a connection; an absent matching connection is a no-op."""

        self._context.remove_link(from_card_id, to_card_id, kind)

    def to_records(self, project_id: str | None = None) -> builtins.list[ConnectionRecord]:
        return self._records_from_cards(CardCollection(self._context).to_records(project_id))

    def _records_from_cards(
        self, cards: Iterable[CardMetadataRecord],
    ) -> builtins.list[ConnectionRecord]:
        records: builtins.list[ConnectionRecord] = []
        for card in cards:
            for link in self._context.list_links(card["card_id"])["outgoing"]:
                records.append({
                    "project_id": card["project_id"],
                    "from_card_id": card["card_id"],
                    "to_card_id": str(link["to_card_id"]),
                    "to_type": str(link["to_type"]),
                    "kind": str(link["kind"]),
                    "label": None if link["label"] is None else str(link["label"]),
                    "created_at": int(link["created_at"]),
                    "to_title": None if link["to_title"] is None else str(link["to_title"]),
                })
        return records

    def to_dataframe(self, project_id: str | None = None) -> pd.DataFrame:
        """Return a detached connection table with the shared record schema."""

        return records_to_dataframe(self.to_records(project_id), CONNECTION_RECORD_FIELDS)


class ProjectCollection:
    """Read projects from a live context and return detached snapshots."""

    __slots__ = ("_context",)

    def __init__(self, context: _native.Context) -> None:
        self._context = context

    def list(self) -> builtins.list[Project]:
        return [Project._from_native(item) for item in self._context.list_projects()]

    def to_records(self) -> builtins.list[ProjectRecord]:
        return [project.to_record() for project in self.list()]

    def to_dataframe(self) -> pd.DataFrame:
        """Return a detached, predictably typed project DataFrame."""

        return records_to_dataframe(self.to_records(), PROJECT_RECORD_FIELDS)


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

    def to_dataframe(
        self, project_id: str | None = None, *, include_content: bool = False
    ) -> pd.DataFrame:
        """Return a detached card DataFrame, optionally including bodies."""

        if include_content:
            return records_to_dataframe(
                self.to_records(project_id, include_content=True),
                COMPLETE_CARD_RECORD_FIELDS,
            )
        return records_to_dataframe(
            self.to_records(project_id), CARD_METADATA_RECORD_FIELDS
        )
