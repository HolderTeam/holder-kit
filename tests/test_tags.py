from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

import holder
from holder import _native


def test_tag_mutations_preserve_core_semantics(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with holder.open(data) as context:
        project = context.create_project("Tags")
        card = context.create_card(project.project_id, "Card", "Prose #Mixed.\n\n#mixed #todo\n")
        assert context.tags.list(card.card_id) == ["mixed", "todo"]
        assert context.tags.list_editable(card.card_id) == ["mixed", "todo"]
        original = context.get_card_content(card.card_id)
        assert context.tags.add(card.card_id, "MIXED") is holder.TagAddResult.ALREADY_PRESENT
        assert context.get_card_content(card.card_id) == original
        assert context.tags.remove(card.card_id, "MiXeD") is holder.TagRemoveResult.REMOVED
        assert context.tags.list(card.card_id) == ["mixed", "todo"]  # prose untouched
        assert context.tags.list_editable(card.card_id) == ["todo"]
        unchanged = context.get_card_content(card.card_id)
        assert context.tags.remove(card.card_id, "mixed") is holder.TagRemoveResult.PRESENT_OUTSIDE_EDITABLE_TAG_LINE
        assert context.tags.remove(card.card_id, "absent") is holder.TagRemoveResult.NOT_PRESENT
        assert context.get_card_content(card.card_id) == unchanged
        assert context.tags.add(card.card_id, "URGENT") is holder.TagAddResult.ADDED
        assert context.tags.remove(card.card_id, "todo") is holder.TagRemoveResult.REMOVED
        records = context.tags.to_records()
        assert records == [
            {"project_id": project.project_id, "card_id": card.card_id, "tag": "mixed", "editable": False},
            {"project_id": project.project_id, "card_id": card.card_id, "tag": "urgent", "editable": True},
        ]
        assert all(tuple(record) == holder.TAG_RECORD_FIELDS for record in records)
        assert "#Mixed" in context.get_card_content(card.card_id)
    assert json.loads(json.dumps(records)) == records
    with holder.open(data) as context:
        assert context.tags.to_records() == records
        context.update_card(card.card_id, "Replaced #replacement")
        assert context.tags.list(card.card_id) == ["replacement"]


def test_tag_queries_and_scoping(tmp_path: Path) -> None:
    with holder.open(tmp_path / "data") as context:
        project = context.create_project("First")
        other = context.create_project("Other")
        first = context.create_card(project.project_id, "First", "#same #same #unique")
        second = context.create_card(project.project_id, "Second", "#SAME")
        outside = context.create_card(other.project_id, "Outside", "#other")
        context.create_card(project.project_id, "No tags")
        assert context.tags.project_counts(project.project_id) == [
            {"project_id": project.project_id, "tag": "same", "count": 2},
            {"project_id": project.project_id, "tag": "unique", "count": 1},
        ]
        matches = context.tags.cards_with_tag(project.project_id, "SAME")
        assert {item["card_id"] for item in matches} == {first.card_id, second.card_id}
        assert {item["title"] for item in matches} == {"First", "Second"}
        assert len(context.tags.to_records(project.project_id)) == 3
        assert len(context.tags.to_records()) == 4
        assert context.tags.to_records(other.project_id)[0]["card_id"] == outside.card_id
        assert context.tags.to_records("missing") == []
        assert context.tags.project_counts("missing") == []
        assert context.tags.cards_with_tag("missing", "same") == []
        assert context.tags.cards_with_tag(project.project_id, "absent") == []


@pytest.mark.parametrize("tag", ["", "#todo", "two words", "bad\x00tag"])
def test_invalid_tag_mutations(tmp_path: Path, tag: str) -> None:
    with holder.open(tmp_path / "data") as context:
        project = context.create_project("Errors")
        card = context.create_card(project.project_id, "Card", "Keep this body")
        for operation in (context.tags.add, context.tags.remove):
            with pytest.raises(ValueError):
                operation(card.card_id, tag)
        assert context.get_card_content(card.card_id) == "Keep this body"


def test_tag_errors_and_closed_context(tmp_path: Path) -> None:
    with holder.open(tmp_path / "data") as context:
        tags = context.tags
        for read in (tags.list, tags.list_editable):
            with pytest.raises(holder.HolderError, match="card not found"):
                read("missing")
            with pytest.raises(ValueError):
                read("")
        for mutation in (tags.add, tags.remove):
            with pytest.raises(holder.HolderError, match="card not found"):
                mutation("missing", "valid")
        with pytest.raises(TypeError):
            tags.add("missing", None)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="embedded null"):
            tags.cards_with_tag("bad\x00id", "tag")
    for closed_read in (tags.list, tags.list_editable, tags.project_counts):
        with pytest.raises(RuntimeError, match="closed"):
            closed_read("id")
    for closed_operation in (tags.add, tags.remove, tags.cards_with_tag):
        with pytest.raises(RuntimeError, match="closed"):
            closed_operation("id", "tag")
    with pytest.raises(RuntimeError, match="closed"):
        tags.to_records()


def test_tag_tables_are_typed_detached_and_joinable(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    data = tmp_path / "data"
    with holder.open(data) as context:
        empty = context.tags.to_dataframe()
        project = context.create_project("Tables")
        other = context.create_project("Other")
        card = context.create_card(project.project_id, "Read", "Prose #read\n\n#todo")
        context.create_card(other.project_id, "Outside", "#outside")
        tables = context.to_dataframes(project.project_id)
        frame = tables["tags"]
        pd.testing.assert_frame_equal(frame, context.tags.to_dataframe(project.project_id))
        assert context.to_dataframes("missing")["tags"].empty
    for table in (empty, frame):
        assert tuple(table.columns) == holder.TAG_RECORD_FIELDS
        assert {str(column): str(dtype) for column, dtype in table.dtypes.items()} == {
            "project_id": "string", "card_id": "string", "tag": "string", "editable": "boolean",
        }
    assert frame["tag"].tolist() == ["read", "todo"]
    assert frame["editable"].tolist() == [False, True]
    joined = frame.merge(tables["cards"], on=["project_id", "card_id"])
    assert joined["title"].tolist() == ["Read", "Read"]
    frame.loc[:, "tag"] = "local"
    with holder.open(data) as context:
        assert context.tags.list(card.card_id) == ["read", "todo"]


def test_tags_exclude_trashed_cards_even_with_stale_index(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with holder.open(data) as context:
        project = context.create_project("Trash")
        card = context.create_card(project.project_id, "Deleted", "#stale")
    # Simulate stale tag rows for a trashed card; Python has no trash API yet.
    database = data / "server" / "holder.db"
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE cards SET deleted_at = 1 WHERE card_id = ?", (card.card_id,))
    with holder.open(data) as context:
        assert context.tags.to_records() == []
        assert context.tags.project_counts(project.project_id) == []
        assert context.tags.cards_with_tag(project.project_id, "stale") == []


def test_tag_read_failure_does_not_return_partial_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with holder.open(tmp_path / "data") as context:
        project = context.create_project("Failure")
        context.create_card(project.project_id, "Tagged", "#tag")

        def fail(self: _native.Context, card_id: str) -> list[str]:
            raise holder.HolderError("tag read failed")

        monkeypatch.setattr(_native.Context, "list_tags", fail)
        with pytest.raises(holder.HolderError, match="tag read failed"):
            context.tags.to_records()
        pytest.importorskip("pandas")
        with pytest.raises(holder.HolderError, match="tag read failed"):
            context.to_dataframes()
