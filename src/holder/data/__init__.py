"""Detached Holder data types organised by domain."""

from .card import CARD_RECORD_FIELDS, Card, CardRecord
from .project import PROJECT_RECORD_FIELDS, Project, ProjectRecord

__all__ = [
    "CARD_RECORD_FIELDS",
    "PROJECT_RECORD_FIELDS",
    "Card",
    "CardRecord",
    "Project",
    "ProjectRecord",
]
