"""Project-scoped adapters over the shared collection operations."""

from __future__ import annotations

import builtins
import json
from typing import TYPE_CHECKING, Any, Iterator, Literal, Mapping, overload

from .collections import (
    CardCollection,
    ConnectionCollection,
    MilestoneCollection,
    TagCollection,
)
from .data import (
    Card,
    CardMetadataRecord,
    CompleteCardRecord,
    ConnectionRecord,
    MilestoneRecord,
    MilestoneUpdate,
    Project,
    ProjectMilestoneRecord,
    ProjectTagRecord,
    TagAddResult,
    TaggedCardRecord,
    TagRecord,
    TagRemoveResult,
)
from .data.card import _complete_record_from_native, _metadata_record_from_native
from . import _native

if TYPE_CHECKING:
    import pandas as pd


class _ProjectCollection:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project


class ProjectCards(_ProjectCollection):
    """Live Card handles or detached record exports belonging to this project."""

    @overload
    def __call__(
        self, *, batch_size: int = 256, include_content: Literal[False] = False,
        tag: str | None = None, roots: bool = False, parent_card_id: str | None = None,
        order: Literal["card_id", "updated"] | None = None,
    ) -> Iterator[builtins.list[CardMetadataRecord]]: ...

    @overload
    def __call__(
        self, *, batch_size: int = 256, include_content: Literal[True],
        tag: str | None = None, roots: bool = False, parent_card_id: str | None = None,
        order: Literal["card_id", "updated"] | None = None,
    ) -> Iterator[builtins.list[CompleteCardRecord]]: ...

    @overload
    def __call__(
        self, *, batch_size: int = 256, include_content: bool,
        tag: str | None = None, roots: bool = False, parent_card_id: str | None = None,
        order: Literal["card_id", "updated"] | None = None,
    ) -> Iterator[builtins.list[CardMetadataRecord] | builtins.list[CompleteCardRecord]]: ...

    def __call__(
        self, *, batch_size: int = 256, include_content: bool = False,
        tag: str | None = None, roots: bool = False, parent_card_id: str | None = None,
        order: Literal["card_id", "updated"] | None = None,
    ) -> Iterator[builtins.list[CardMetadataRecord] | builtins.list[CompleteCardRecord]]:
        """Lazily yield detached record batches; the last may be smaller.

        Metadata reads omit bodies and follow Core's recency order. Complete
        reads follow card ID order, unless order is supplied. Tag and hierarchy
        filters combine before pagination. There is no snapshot across page reads.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size must be a positive integer")
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if not isinstance(include_content, bool):
            raise TypeError("include_content must be a bool")
        if not isinstance(roots, bool):
            raise TypeError("roots must be a bool")
        for name, value in (("tag", tag), ("parent_card_id", parent_card_id)):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if value == "":
                raise ValueError(f"{name} must not be empty")
        if roots and parent_card_id is not None:
            raise ValueError("roots and parent_card_id cannot be combined")
        if order is not None and order not in ("card_id", "updated"):
            raise ValueError("order must be 'card_id' or 'updated'")
        self._project._live_context()
        request: dict[str, Any] | None = None
        if tag is not None or roots or parent_card_id is not None or order is not None:
            if not _native.CARD_COLLECTION_SUPPORTED:
                raise NotImplementedError(
                    "Filtered card batches require a Core SDK with collection pagination support"
                )
            request = {
                "view": "children" if parent_card_id is not None else "roots" if roots else "all",
                "include_content": include_content,
                "order": order or ("card_id" if include_content else "updated"),
            }
            if tag is not None:
                request["tag"] = tag
            if parent_card_id is not None:
                request["parent_card_id"] = parent_card_id
        return self._batches(batch_size, include_content, request)

    def _pages(
        self, batch_size: int, include_content: bool, collection_request: dict[str, Any] | None,
    ) -> Iterator[builtins.list[Mapping[str, Any]]]:
        limit = min(batch_size, _native.CARD_PAGE_MAX_LIMIT)
        cursor: str | None = None
        request: dict[str, Any] = {"view": "recent", "limit": limit}
        if collection_request is not None:
            collection_request = {**collection_request, "limit": limit}
        while True:
            context = self._project._live_context()
            if collection_request is not None:
                page = context.collection_cards_page(self._project.project_id, json.dumps(collection_request))
                collection_request["cursor"] = page["next_cursor"]
                finished = page["next_cursor"] is None
            elif include_content:
                page = context.list_complete_cards_page(self._project.project_id, cursor, limit)
                cursor = page["next_cursor"]
                finished = cursor is None
            else:
                page = context.query_cards(self._project.project_id, json.dumps(request))
                finished = len(page["cards"]) < limit
                if page["cards"]:
                    last = page["cards"][-1]
                    request["before_updated_at"] = last["updated_at"]
                    request["before_card_id"] = last["card_id"]
            if page["cards"]:
                yield page["cards"]
            if finished:
                return

    def _batches(
        self, batch_size: int, include_content: bool, collection_request: dict[str, Any] | None,
    ) -> Iterator[builtins.list[CardMetadataRecord] | builtins.list[CompleteCardRecord]]:
        pending: builtins.list[Mapping[str, Any]] = []
        for page in self._pages(batch_size, include_content, collection_request):
            pending.extend(page)
            while len(pending) >= batch_size:
                records, pending = pending[:batch_size], pending[batch_size:]
                self._project._live_context()
                if include_content:
                    yield [_complete_record_from_native(record) for record in records]
                else:
                    yield [_metadata_record_from_native(record) for record in records]
        if pending:
            self._project._live_context()
            if include_content:
                yield [_complete_record_from_native(record) for record in pending]
            else:
                yield [_metadata_record_from_native(record) for record in pending]

    def list(self) -> builtins.list[Card]:
        return [Card._from_native(record, self._project) for record in
                self._project._live_context().list_cards(self._project.project_id)]

    def trashed(self) -> builtins.list[Card]:
        """Find live Card handles for the project's Trash, including after reopening."""
        return [Card._from_native(record, self._project) for record in
                self._project._live_context().list_trashed_cards(self._project.project_id)]

    @overload
    def to_records(
        self, *, include_content: Literal[False] = False
    ) -> builtins.list[CardMetadataRecord]: ...

    @overload
    def to_records(
        self, *, include_content: Literal[True]
    ) -> builtins.list[CompleteCardRecord]: ...

    def to_records(
        self,
        *,
        include_content: bool = False,
    ) -> builtins.list[CardMetadataRecord] | builtins.list[CompleteCardRecord]:
        cards = CardCollection(self._project._live_context())
        if include_content:
            return cards.to_records(self._project.project_id, include_content=True)
        return cards.to_records(self._project.project_id)

    def to_dataframe(self, *, include_content: bool = False) -> pd.DataFrame:
        return CardCollection(self._project._live_context()).to_dataframe(
            self._project.project_id,
            include_content=include_content,
        )


class ProjectConnections(_ProjectCollection):
    """Outgoing connections from this project's cards, including external targets."""

    def add(
        self, from_card_id: str, to_card_id: str, kind: str, label: str | None = None
    ) -> None:
        self._project._require_card(from_card_id)
        ConnectionCollection(self._project._live_context()).add(
            from_card_id, to_card_id, kind, label
        )

    def remove(self, from_card_id: str, to_card_id: str, kind: str) -> None:
        self._project._require_card(from_card_id)
        ConnectionCollection(self._project._live_context()).remove(
            from_card_id, to_card_id, kind
        )

    def to_records(self) -> list[ConnectionRecord]:
        return ConnectionCollection(self._project._live_context()).to_records(
            self._project.project_id
        )

    def to_dataframe(self) -> pd.DataFrame:
        return ConnectionCollection(self._project._live_context()).to_dataframe(
            self._project.project_id
        )


class ProjectTags(_ProjectCollection):
    """Read and edit tags on this project's cards."""

    def list(self, card_id: str) -> builtins.list[str]:
        self._project._require_card(card_id)
        return TagCollection(self._project._live_context()).list(card_id)

    def list_editable(self, card_id: str) -> builtins.list[str]:
        self._project._require_card(card_id)
        return TagCollection(self._project._live_context()).list_editable(card_id)

    def add(self, card_id: str, tag: str) -> TagAddResult:
        self._project._require_card(card_id)
        return TagCollection(self._project._live_context()).add(card_id, tag)

    def remove(self, card_id: str, tag: str) -> TagRemoveResult:
        self._project._require_card(card_id)
        return TagCollection(self._project._live_context()).remove(card_id, tag)

    def project_counts(self) -> builtins.list[ProjectTagRecord]:
        return TagCollection(self._project._live_context()).project_counts(
            self._project.project_id
        )

    def cards_with_tag(self, tag: str) -> builtins.list[TaggedCardRecord]:
        return TagCollection(self._project._live_context()).cards_with_tag(
            self._project.project_id, tag
        )

    def to_records(self) -> builtins.list[TagRecord]:
        return TagCollection(self._project._live_context()).to_records(
            self._project.project_id
        )

    def to_dataframe(self) -> pd.DataFrame:
        return TagCollection(self._project._live_context()).to_dataframe(
            self._project.project_id
        )


class ProjectMilestones(_ProjectCollection):
    """Card milestones and calendar exports scoped to one project."""

    def list(self, card_id: str) -> builtins.list[MilestoneRecord]:
        self._project._require_card(card_id)
        return MilestoneCollection(self._project._live_context()).list(card_id)

    def add(
        self,
        card_id: str,
        start_at: int,
        *,
        end_at: int | None = None,
        all_day: bool = False,
        kind: str | None = None,
        description: str | None = None,
    ) -> builtins.list[MilestoneRecord]:
        self._project._require_card(card_id)
        return MilestoneCollection(self._project._live_context()).add(
            card_id,
            start_at,
            end_at=end_at,
            all_day=all_day,
            kind=kind,
            description=description,
        )

    def update(
        self, card_id: str, milestone_id: str, changes: MilestoneUpdate
    ) -> MilestoneRecord:
        self._project._require_card(card_id)
        return MilestoneCollection(self._project._live_context()).update(
            self._project.project_id,
            card_id,
            milestone_id,
            changes,
        )

    def remove(self, card_id: str, milestone_id: str) -> None:
        self._project._require_card(card_id)
        MilestoneCollection(self._project._live_context()).remove(card_id, milestone_id)

    def in_range(
        self, from_at: int, to_at: int
    ) -> builtins.list[ProjectMilestoneRecord]:
        return MilestoneCollection(self._project._live_context()).in_range(
            self._project.project_id,
            from_at,
            to_at,
        )

    def to_records(self) -> builtins.list[ProjectMilestoneRecord]:
        return MilestoneCollection(self._project._live_context()).to_records(
            self._project.project_id
        )

    def to_dataframe(self) -> pd.DataFrame:
        return MilestoneCollection(self._project._live_context()).to_dataframe(
            self._project.project_id
        )
