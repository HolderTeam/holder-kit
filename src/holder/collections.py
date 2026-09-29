"""Live collection facades which produce detached Holder models and records."""

from __future__ import annotations

import builtins

from . import _native
from .data.card import Card, CardRecord
from .data.project import Project, ProjectRecord


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
    """Read complete cards from a live context and return detached snapshots."""

    __slots__ = ("_context",)

    def __init__(self, context: _native.Context) -> None:
        self._context = context

    def list(self, project_id: str | None = None) -> builtins.list[Card]:
        project_ids = (
            [project_id]
            if project_id is not None
            else [item["project_id"] for item in self._context.list_projects()]
        )
        cards: builtins.list[Card] = []
        for current_project_id in project_ids:
            for metadata in self._context.list_cards(current_project_id):
                content = self._context.get_card_content(metadata["card_id"])
                cards.append(Card._from_native(metadata, content))
        return cards

    def to_records(
        self, project_id: str | None = None
    ) -> builtins.list[CardRecord]:
        return [card.to_record() for card in self.list(project_id)]
