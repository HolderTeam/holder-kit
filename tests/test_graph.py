from __future__ import annotations

import sys
from pathlib import Path

import pytest

import holderkit
from holderkit.graph import records_to_networkx


def test_graph_preserves_direction_parallel_edges_isolates_and_detachment(tmp_path: Path) -> None:
    nx = pytest.importorskip("networkx")
    data = tmp_path / "data"
    with holderkit.open(data) as context:
        project = context.create_project("Graph")
        source = context.create_card(project.project_id, "Source", "body")
        target = context.create_card(project.project_id, "Target", parent_card_id=source.card_id)
        isolated = context.create_card(project.project_id, "Isolated")
        context.connections.add(source.card_id, target.card_id, "depends_on", "label")
        context.connections.add(source.card_id, target.card_id, "references")
        context.connections.add(target.card_id, source.card_id, "references")
        context.connections.add(source.card_id, source.card_id, "custom")
        graph = context.to_networkx(project.project_id)
        complete = context.to_networkx(include_content=True)
    assert isinstance(graph, nx.MultiDiGraph)
    assert set(graph) == {source.card_id, target.card_id, isolated.card_id}
    assert graph.number_of_edges() == 4
    assert graph.degree(isolated.card_id) == 0
    assert graph[source.card_id][target.card_id]["depends_on"]["label"] == "label"
    assert "content" not in graph.nodes[source.card_id]
    assert complete.nodes[source.card_id]["content"] == "body"
    assert graph.nodes[target.card_id]["parent_card_id"] == source.card_id
    graph.nodes[source.card_id]["title"] = "local change"
    graph.remove_edge(source.card_id, target.card_id, "depends_on")
    with holderkit.open(data) as context:
        persisted = context.to_networkx()
        assert persisted.nodes[source.card_id]["title"] == "Source"
        assert persisted.number_of_edges() == 4


def test_empty_and_project_scoped_graph(tmp_path: Path) -> None:
    pytest.importorskip("networkx")
    with holderkit.open(tmp_path / "data") as context:
        assert len(context.to_networkx()) == 0
        first = context.create_project("First")
        second = context.create_project("Second")
        source = context.create_card(first.project_id, "Source")
        target = context.create_card(second.project_id, "External")
        isolated = context.create_card(second.project_id, "Other")
        context.connections.add(source.card_id, target.card_id, "references")
        graph = context.to_networkx(first.project_id)
        assert set(graph) == {source.card_id, target.card_id}
        assert graph.nodes[source.card_id]["exported"] is True
        assert graph.nodes[target.card_id] == {
            "card_id": target.card_id, "title": "External", "exported": False,
        }
        assert isolated.card_id not in graph
        whole = context.to_networkx()
        assert whole.nodes[target.card_id]["exported"] is True


def test_optional_networkx_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "networkx", None)
    with holderkit.open(tmp_path / "data") as context:
        with pytest.raises(ModuleNotFoundError, match=r"holder-kit\[graph\]"):
            context.to_networkx()


def test_unresolved_card_and_non_card_targets_in_detached_records(tmp_path: Path) -> None:
    pytest.importorskip("networkx")
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Detached adapters")
        source = context.create_card(project.project_id, "Source")
        cards = context.cards.to_records()
    unresolved: holderkit.ConnectionRecord = {
        "project_id": project.project_id, "from_card_id": source.card_id,
        "to_card_id": "unknown-card", "to_type": "card", "kind": "references",
        "label": None, "created_at": source.created_at, "to_title": None,
    }
    resource: holderkit.ConnectionRecord = {
        **unresolved, "to_card_id": "resource-id", "to_type": "resource",
        "kind": "attachment",
    }
    graph = records_to_networkx(cards, [unresolved, resource])
    assert graph.nodes["unknown-card"] == {
        "card_id": "unknown-card", "title": None, "exported": False,
    }
    assert "resource-id" not in graph
    assert graph.number_of_edges() == 1


def test_metadata_graph_does_not_require_card_bodies(tmp_path: Path) -> None:
    pytest.importorskip("networkx")
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Metadata graph")
        card = context.create_card(project.project_id, "Missing body", "body")
        (Path(project.root_path) / card.rel_path).unlink()
        graph = context.to_networkx()
        assert graph.nodes[card.card_id]["title"] == "Missing body"
        with pytest.raises(holderkit.HolderError, match="card content missing"):
            context.to_networkx(include_content=True)
