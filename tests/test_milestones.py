from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, cast

import pytest

import holderkit
from holderkit import _native


def test_milestone_lifecycle_and_partial_updates(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with holderkit.open(data) as context:
        project = context.create_project("Calendar")
        card = context.create_card(project.project_id, "Event", "Body #keep")
        assert context.milestones.list(card.card_id) == []
        first = context.milestones.add(card.card_id, 200, end_at=300, kind="Appointment", description="Café")
        assert len(first) == 1
        milestone = first[0]
        assert tuple(milestone) == holderkit.MILESTONE_RECORD_FIELDS
        assert milestone["card_id"] == card.card_id
        assert milestone["description"] == "Café"
        assert milestone["all_day"] is False
        second = context.milestones.add(card.card_id, 100, all_day=True)
        assert [row["start_at"] for row in second] == [100, 200]
        assert second[0]["end_at"] is None
        assert second[0]["kind"] is None and second[0]["description"] is None
        updated = context.milestones.update(project.project_id, card.card_id, milestone["milestone_id"], {
            "start_at": 150, "all_day": True, "end_at": None,
        })
        assert updated["start_at"] == 150 and updated["all_day"] is True
        assert updated["end_at"] is None
        assert updated["description"] == "Café" and updated["kind"] == "Appointment"
        cleared = context.milestones.update(project.project_id, card.card_id, milestone["milestone_id"], {
            "kind": None, "description": None,
        })
        assert cleared["kind"] is None and cleared["description"] is None
        assert cleared["created_at"] == milestone["created_at"]
        assert context.milestones.update(project.project_id, card.card_id, milestone["milestone_id"], {}) == cleared
        assert context.get_card_content(card.card_id) == "Body #keep"
        assert context.tags.list(card.card_id) == ["keep"]
        records = context.milestones.to_records(project.project_id)
        assert all(tuple(row) == holderkit.PROJECT_MILESTONE_RECORD_FIELDS for row in records)
        assert all(row["project_id"] == project.project_id and row["card_title"] == "Event" for row in records)
    assert json.loads(json.dumps(records)) == records
    with holderkit.open(data) as context:
        assert context.milestones.to_records() == records
        context.milestones.remove(card.card_id, milestone["milestone_id"])
        context.milestones.remove(card.card_id, milestone["milestone_id"])
        assert len(context.milestones.list(card.card_id)) == 1


def test_milestone_ownership_and_range_contract(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("First")
        other = context.create_project("Other")
        first = context.create_card(project.project_id, "First")
        second = context.create_card(project.project_id, "Second")
        outside = context.create_card(other.project_id, "Outside")
        context.milestones.add(first.card_id, 0, end_at=200)  # overlap isn't enough
        target = context.milestones.add(first.card_id, 100)[1]
        context.milestones.add(second.card_id, 200)
        context.milestones.add(outside.card_id, 150)
        ranged = context.milestones.in_range(project.project_id, 100, 200)
        assert [row["start_at"] for row in ranged] == [100, 200]
        assert [row["card_title"] for row in ranged] == ["First", "Second"]
        assert context.milestones.in_range(project.project_id, 100, 100)[0]["milestone_id"] == target["milestone_id"]
        assert context.milestones.in_range(project.project_id, 200, 100) == []
        assert context.milestones.in_range("missing", 0, 300) == []
        assert context.milestones.to_records("missing") == []
        assert len(context.milestones.to_records()) == 4
        assert len(context.milestones.to_records(other.project_id)) == 1
        context.milestones.remove(second.card_id, target["milestone_id"])  # different owner: no-op
        assert len(context.milestones.list(first.card_id)) == 2
        for project_id, card_id, milestone_id in (
            (other.project_id, first.card_id, target["milestone_id"]),
            (project.project_id, second.card_id, target["milestone_id"]),
            (project.project_id, first.card_id, "missing"),
        ):
            with pytest.raises(holderkit.HolderError, match="milestone not found"):
                context.milestones.update(project_id, card_id, milestone_id, {"kind": "wrong"})
        with pytest.raises(holderkit.HolderError, match="end_at must not be before start_at"):
            context.milestones.update(project.project_id, first.card_id, target["milestone_id"], {"end_at": 99})
        assert context.milestones.list(first.card_id)[1] == target


@pytest.mark.parametrize("changes,exception", [
    ({"start_at": None}, ValueError), ({"all_day": None}, ValueError),
    ({"start_at": True}, TypeError), ({"end_at": 1.5}, TypeError),
    ({"all_day": 1}, TypeError), ({"kind": 12}, TypeError),
    ({"description": []}, TypeError), ({"unknown": "ignored?"}, ValueError),
    ({"start_at": 2**63}, OverflowError), ({"end_at": -(2**63) - 1}, OverflowError),
])
def test_milestone_update_rejects_invalid_inputs(
    tmp_path: Path, changes: dict[str, Any], exception: type[Exception],
) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Validation")
        card = context.create_card(project.project_id, "Card")
        original = context.milestones.add(card.card_id, 100)[0]
        with pytest.raises(exception):
            context.milestones.update(project.project_id, card.card_id, original["milestone_id"], cast(holderkit.MilestoneUpdate, changes))
        assert context.milestones.list(card.card_id) == [original]


def test_milestone_native_argument_errors_and_closed_context(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Errors")
        card = context.create_card(project.project_id, "Card")
        milestones = context.milestones
        invalid_timestamps: list[Any] = [None, True, 1.5, "100"]
        for timestamp in invalid_timestamps:
            with pytest.raises(TypeError):
                milestones.add(card.card_id, timestamp)
            with pytest.raises(TypeError):
                milestones.in_range(project.project_id, timestamp, 1)
            if timestamp is not None:
                with pytest.raises(TypeError):
                    milestones.add(card.card_id, 0, end_at=timestamp)
        with pytest.raises(TypeError):
            milestones.add(card.card_id, 0, all_day=1)  # type: ignore[arg-type]
        with pytest.raises(OverflowError):
            milestones.add(card.card_id, 2**63)
        with pytest.raises(OverflowError):
            milestones.in_range(project.project_id, -(2**63) - 1, 0)
        with pytest.raises(ValueError, match="embedded null"):
            milestones.add(card.card_id, 0, kind="bad\x00kind")
        with pytest.raises(holderkit.HolderError, match="card not found"):
            milestones.list("missing")
        with pytest.raises(ValueError):
            milestones.list("")
        with pytest.raises(holderkit.HolderError, match="card not found"):
            milestones.add("missing", 0)
        with pytest.raises(holderkit.HolderError, match="card not found"):
            milestones.remove("missing", "id")
        # Native keyword entry points use the same ownership-safe operations.
        assert context._context.list_milestones(card_id=card.card_id) == []
        assert context._context.milestones_in_range(project_id=project.project_id, from_at=0, to_at=1) == []
    for operation in (
        lambda: milestones.list(card.card_id), lambda: milestones.to_records(),
        lambda: milestones.add(card.card_id, 0), lambda: milestones.remove(card.card_id, "id"),
        lambda: milestones.update(project.project_id, card.card_id, "id", {}),
        lambda: milestones.in_range(project.project_id, 0, 1),
    ):
        with pytest.raises(RuntimeError, match="closed"):
            operation()


def test_milestone_dataframe_contract_and_detachment(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    data = tmp_path / "data"
    with holderkit.open(data) as context:
        empty = context.milestones.to_dataframe()
        project = context.create_project("Frames")
        other = context.create_project("Other")
        card = context.create_card(project.project_id, "Calendar card")
        outside = context.create_card(other.project_id, "Outside")
        context.milestones.add(card.card_id, 0, all_day=True)
        context.milestones.add(card.card_id, 100, end_at=200, kind="Custom", description="Body")
        context.milestones.add(outside.card_id, 300)
        tables = context.to_dataframes(project.project_id, include_content=True)
        frame = tables["milestones"]
        pd.testing.assert_frame_equal(frame, context.milestones.to_dataframe(project.project_id))
        assert context.to_dataframes("missing")["milestones"].empty
    timestamp_fields = {"start_at", "end_at", "created_at", "updated_at"}
    dtypes = {field: "datetime64[ns, UTC]" if field in timestamp_fields else "string"
              for field in holderkit.PROJECT_MILESTONE_RECORD_FIELDS}
    dtypes["all_day"] = "boolean"
    for table in (empty, frame):
        assert tuple(table.columns) == holderkit.PROJECT_MILESTONE_RECORD_FIELDS
        assert {str(column): str(dtype) for column, dtype in table.dtypes.items()} == dtypes
    assert pd.isna(frame.iloc[0]["end_at"]) and pd.isna(frame.iloc[0]["kind"])
    assert frame.iloc[0]["start_at"] == pd.Timestamp(0, unit="s", tz="UTC")
    assert frame.iloc[1]["end_at"] == pd.Timestamp(200, unit="s", tz="UTC")
    assert frame["all_day"].tolist() == [True, False]
    joined = frame.merge(tables["cards"], on=["project_id", "card_id"])
    assert joined["title"].tolist() == ["Calendar card", "Calendar card"]
    frame.loc[:, "kind"] = "local"
    with holderkit.open(data) as context:
        assert context.milestones.list(card.card_id)[1]["kind"] == "Custom"


def test_milestone_queries_exclude_trashed_cards(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with holderkit.open(data) as context:
        project = context.create_project("Trash")
        card = context.create_card(project.project_id, "Deleted")
        milestone = context.milestones.add(card.card_id, 100)[0]
    with sqlite3.connect(data / "server" / "holder.db") as database:
        database.execute("UPDATE cards SET deleted_at = 1 WHERE card_id = ?", (card.card_id,))
    with holderkit.open(data) as context:
        assert context.milestones.to_records() == []
        assert context.milestones.in_range(project.project_id, 0, 200) == []
        with pytest.raises(holderkit.HolderError, match="milestone not found"):
            context.milestones.update(project.project_id, card.card_id, milestone["milestone_id"], {})


def test_missing_body_mutation_failure_preserves_core_index_semantics(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Missing body")
        card = context.create_card(project.project_id, "Card")
        original = context.milestones.add(card.card_id, 100)[0]
        (Path(project.root_path) / card.rel_path).unlink()
        # Updates check the durable file before replacing index rows.
        with pytest.raises(holderkit.HolderError, match="card content missing"):
            context.milestones.update(project.project_id, card.card_id, original["milestone_id"], {"kind": "new"})
        assert context.milestones.list(card.card_id) == [original]
        # Existing core add/remove replace index rows BEFORE writing the file.
        # An exception therefore cannot imply rollback of their index changes.
        with pytest.raises(holderkit.HolderError, match="card content missing"):
            context.milestones.add(card.card_id, 200)
        assert [row["start_at"] for row in context.milestones.list(card.card_id)] == [100, 200]
        with pytest.raises(holderkit.HolderError, match="card content missing"):
            context.milestones.remove(card.card_id, original["milestone_id"])
        assert [row["start_at"] for row in context.milestones.list(card.card_id)] == [200]


def test_milestone_read_failure_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Failure")
        context.create_card(project.project_id, "Card")

        def fail(self: _native.Context, card_id: str) -> list[dict[str, Any]]:
            raise holderkit.HolderError("milestone read failed")

        monkeypatch.setattr(_native.Context, "list_milestones", fail)
        with pytest.raises(holderkit.HolderError, match="milestone read failed"):
            context.milestones.to_records()
        pytest.importorskip("pandas")
        with pytest.raises(holderkit.HolderError, match="milestone read failed"):
            context.to_dataframes()
