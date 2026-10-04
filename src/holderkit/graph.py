"""Optional NetworkX conversion over shared detached record contracts."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Iterable, cast

from .data import CardMetadataRecord, CompleteCardRecord, ConnectionRecord

if TYPE_CHECKING:
    import networkx as nx


def records_to_networkx(
    cards: Iterable[CardMetadataRecord | CompleteCardRecord],
    connections: Iterable[ConnectionRecord],
) -> nx.MultiDiGraph[str]:
    """Copy card records and explicit card connections into a directed multigraph."""

    try:
        networkx = import_module("networkx")
    except ModuleNotFoundError as error:
        if error.name != "networkx":
            raise
        raise ModuleNotFoundError(
            'networkx is required for graph support; install "holder-kit[graph]" '
            'or "pip install -e \'.[graph]\'" from a source checkout'
        ) from None

    graph = networkx.MultiDiGraph()
    for card in cards:
        graph.add_node(card["card_id"], **card, exported=True)
    for connection in connections:
        if connection["to_type"] != "card":
            continue
        target = connection["to_card_id"]
        if target not in graph:
            graph.add_node(target, card_id=target, title=connection["to_title"], exported=False)
        graph.add_edge(
            connection["from_card_id"], target,
            key=connection["kind"], **connection,
        )
    return cast("nx.MultiDiGraph[str]", graph)
