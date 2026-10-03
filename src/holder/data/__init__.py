"""Detached Holder data types organised by domain."""

from .card import (
    CARD_METADATA_RECORD_FIELDS,
    CARD_RECORD_FIELDS,
    COMPLETE_CARD_RECORD_FIELDS,
    Card,
    CardMetadataRecord,
    CardRecord,
    CompleteCardRecord,
)
from .project import PROJECT_RECORD_FIELDS, Project, ProjectRecord
from .connection import CONNECTION_RECORD_FIELDS, ConnectionRecord
from .tag import TAG_RECORD_FIELDS, ProjectTagRecord, TaggedCardRecord, TagRecord, TagAddResult, TagRemoveResult

__all__ = [
    "TAG_RECORD_FIELDS", "ProjectTagRecord", "TaggedCardRecord", "TagRecord", "TagAddResult", "TagRemoveResult",
    "CONNECTION_RECORD_FIELDS",
    "ConnectionRecord",
    "CARD_METADATA_RECORD_FIELDS",
    "CARD_RECORD_FIELDS",
    "COMPLETE_CARD_RECORD_FIELDS",
    "PROJECT_RECORD_FIELDS",
    "Card",
    "CardMetadataRecord",
    "CardRecord",
    "CompleteCardRecord",
    "Project",
    "ProjectRecord",
]
