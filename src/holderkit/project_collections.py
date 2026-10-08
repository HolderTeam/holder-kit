"""Project-scoped adapters over the shared collection operations."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Literal, overload

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

if TYPE_CHECKING:
    import pandas as pd


class _ProjectCollection:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project


class ProjectCards(_ProjectCollection):
    """Cards belonging to this project; exported values are detached."""

    def list(self) -> builtins.list[Card]:
        return CardCollection(self._project._live_context()).list(
            self._project.project_id
        )

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
