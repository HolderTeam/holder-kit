from __future__ import annotations

import json
from pathlib import Path

import pytest

import holderkit


def test_connection_lifecycle_and_detached_records(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with holderkit.open(data) as context:
        project = context.create_project("Connections")
        other = context.create_project("Other")
        source = context.create_card(project.project_id, "Source", "[[Target]]")
        target = context.create_card(project.project_id, "Target", parent_card_id=source.card_id)
        context.create_card(other.project_id, "Unconnected")
        assert context.connections.to_records() == []  # hierarchy/inline links excluded
        context.connections.add(source.card_id, target.card_id, "depends_on", "first")
        context.connections.add(source.card_id, target.card_id, "depends_on", "updated")
        context.connections.add(source.card_id, target.card_id, "custom_kind")
        context.connections.add(target.card_id, source.card_id, "depends_on")
        records = context.connections.to_records(project.project_id)
        assert len(records) == 3  # upsert, parallel kinds, reverse direction
        assert len(context._context.list_links(target.card_id)["backlinks"]) == 2
        assert context.connections.to_records(other.project_id) == []
        assert all(tuple(record) == holderkit.CONNECTION_RECORD_FIELDS for record in records)
        assert all(record["project_id"] == project.project_id for record in records)
        edge = next(record for record in records if record["label"] == "updated")
        assert edge["to_title"] == "Target"
        assert edge["to_type"] == "card"
        assert isinstance(edge["created_at"], int)
        context.connections.remove(source.card_id, target.card_id, "custom_kind")
        context.connections.remove(source.card_id, target.card_id, "custom_kind")
        assert len(context.connections.to_records()) == 2
    assert json.loads(json.dumps(records)) == records
    with holderkit.open(data) as context:
        assert len(context.connections.to_records()) == 2


def test_connection_errors_and_closed_context(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Errors")
        card = context.create_card(project.project_id, "Card")
        connections = context.connections
        with pytest.raises(ValueError):
            connections.add(card.card_id, card.card_id, "")
        with pytest.raises(holderkit.HolderError, match="card not found"):
            connections.add(card.card_id, "missing", "depends_on")
        with pytest.raises(ValueError, match="embedded null"):
            connections.add(card.card_id, card.card_id, "bad\x00kind")
        with pytest.raises(holderkit.HolderError, match="card not found"):
            context._context.list_links("missing")
    with pytest.raises(RuntimeError, match="closed"):
        connections.to_records()
    with pytest.raises(RuntimeError, match="closed"):
        connections.add(card.card_id, card.card_id, "depends_on")
    with pytest.raises(RuntimeError, match="closed"):
        connections.remove(card.card_id, card.card_id, "depends_on")


def test_connection_dataframe_contract_and_join(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    with holderkit.open(tmp_path / "data") as context:
        empty = context.connections.to_dataframe()
        project = context.create_project("Table")
        source = context.create_card(project.project_id, "Source")
        target = context.create_card(project.project_id, "Target")
        context.connections.add(source.card_id, target.card_id, "depends_on")
        table = context.connections.to_dataframe()
        cards = context.cards.to_dataframe()
    expected = {field: "string" for field in holderkit.CONNECTION_RECORD_FIELDS}
    expected["created_at"] = "datetime64[ns, UTC]"
    for frame in (empty, table):
        assert list(frame.columns) == list(holderkit.CONNECTION_RECORD_FIELDS)
        assert {str(column): str(dtype) for column, dtype in frame.dtypes.items()} == expected
    assert pd.isna(table.iloc[0]["label"])
    joined = table.merge(cards, left_on="from_card_id", right_on="card_id")
    assert joined.iloc[0]["title"] == "Source"
