"""Card-scoped adapters over the existing Project and Core operations."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from .collections import ConnectionCollection, TagCollection
from .data import Card, ConnectionRecord, MilestoneRecord, MilestoneUpdate, TagAddResult, TagRecord, TagRemoveResult
from .data.card import CardMetadataRecord, _metadata_record_from_native
from .data.project import Project
from .data.connection import CONNECTION_RECORD_FIELDS
from .data.milestone import MILESTONE_RECORD_FIELDS
from .data.tag import TAG_RECORD_FIELDS
from .dataframe import records_to_dataframe

if TYPE_CHECKING:
    import pandas as pd


class _CardCollection:
    __slots__ = ("_card",)

    def __init__(self, card: Card) -> None:
        self._card = card

    def _record(self) -> CardMetadataRecord:
        record = self._card._current()
        if record["deleted_at"] is not None:
            raise ValueError("Card is in Trash; restore it before using its collections")
        return _metadata_record_from_native(record)

    def _project(self) -> Project:
        self._record()
        return self._card.project


class CardTags(_CardCollection):
    """Read and edit this card's tags using Holder's semantic tag operations."""

    def list(self) -> builtins.list[str]:
        return self._project().tags.list(self._card.card_id)

    def list_editable(self) -> builtins.list[str]:
        return self._project().tags.list_editable(self._card.card_id)

    def add(self, tag: str) -> TagAddResult:
        return self._project().tags.add(self._card.card_id, tag)

    def remove(self, tag: str) -> TagRemoveResult:
        return self._project().tags.remove(self._card.card_id, tag)

    def to_records(self) -> builtins.list[TagRecord]:
        record = self._record()
        return TagCollection(self._card.project._live_context())._records_from_cards([record])

    def to_dataframe(self) -> pd.DataFrame:
        return records_to_dataframe(self.to_records(), TAG_RECORD_FIELDS)


class CardConnections(_CardCollection):
    """Edit and export this card's explicit outgoing connections."""

    def _target(self, target: Card, *, require_live: bool = True) -> None:
        if not isinstance(target, Card):
            raise TypeError("target must be a Card")
        if target.project._context is not self._card.project._context:
            raise ValueError("Target Card must belong to the same Context")
        # A target may belong to another project in the same context, as with
        # Project connections; its own owner and current live state still apply.
        record = target._current()
        if require_live and record["deleted_at"] is not None:
            raise ValueError("Target Card is in Trash")

    def add(self, target: Card, kind: str, label: str | None = None) -> None:
        project = self._project()
        self._target(target)
        project.connections.add(self._card.card_id, target.card_id, kind, label)

    def remove(self, target: Card, kind: str) -> None:
        project = self._project()
        self._target(target, require_live=False)
        project.connections.remove(self._card.card_id, target.card_id, kind)

    def to_records(self) -> builtins.list[ConnectionRecord]:
        record = self._record()
        return ConnectionCollection(self._card.project._live_context())._records_from_cards([record])

    def to_dataframe(self) -> pd.DataFrame:
        return records_to_dataframe(self.to_records(), CONNECTION_RECORD_FIELDS)


class CardMilestones(_CardCollection):
    """Read and edit this card's milestones; returned records are detached."""

    def list(self) -> builtins.list[MilestoneRecord]:
        return self._project().milestones.list(self._card.card_id)

    def add(
        self, start_at: int, *, end_at: int | None = None, all_day: bool = False,
        kind: str | None = None, description: str | None = None,
    ) -> builtins.list[MilestoneRecord]:
        """Return the updated full milestone list, matching the Project operation."""
        return self._project().milestones.add(
            self._card.card_id, start_at, end_at=end_at, all_day=all_day,
            kind=kind, description=description,
        )

    def update(self, milestone_id: str, changes: MilestoneUpdate) -> MilestoneRecord:
        return self._project().milestones.update(self._card.card_id, milestone_id, changes)

    def remove(self, milestone_id: str) -> None:
        self._project().milestones.remove(self._card.card_id, milestone_id)

    def to_records(self) -> builtins.list[MilestoneRecord]:
        return self.list()

    def to_dataframe(self) -> pd.DataFrame:
        return records_to_dataframe(self.to_records(), MILESTONE_RECORD_FIELDS)
