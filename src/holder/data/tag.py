"""Detached tag contracts and semantic mutation results."""

from enum import IntEnum
from typing import TypedDict


class TagAddResult(IntEnum):
    ADDED = 0
    ALREADY_PRESENT = 1


class TagRemoveResult(IntEnum):
    REMOVED = 0
    NOT_PRESENT = 1
    PRESENT_OUTSIDE_EDITABLE_TAG_LINE = 2


class TagRecord(TypedDict):
    """One normalized tag membership of a live card; no synthetic tag ID."""

    project_id: str
    card_id: str
    tag: str
    editable: bool


class ProjectTagRecord(TypedDict):
    project_id: str
    tag: str
    count: int


class TaggedCardRecord(TypedDict):
    card_id: str
    title: str


TAG_RECORD_FIELDS: tuple[str, ...] = ("project_id", "card_id", "tag", "editable")
