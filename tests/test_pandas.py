from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import holder
from holder import _native


CARD_METADATA_DTYPES = {
    "card_id": "string",
    "project_id": "string",
    "title": "string",
    "rel_path": "string",
    "parent_card_id": "string",
    "sort_key": "float64",
    "created_at": "datetime64[ns, UTC]",
    "updated_at": "datetime64[ns, UTC]",
    "deleted_at": "datetime64[ns, UTC]",
}

PROJECT_DTYPES = {
    "project_id": "string",
    "name": "string",
    "root_path": "string",
    "privacy_mode": "string",
    "id_scheme": "string",
    "created_at": "datetime64[ns, UTC]",
    "updated_at": "datetime64[ns, UTC]",
    "git_remote_url": "string",
    "git_provider": "string",
    "project_key_id": "string",
}

CONNECTION_DTYPES = {
    field: "datetime64[ns, UTC]" if field == "created_at" else "string"
    for field in holder.CONNECTION_RECORD_FIELDS
}


def _dtypes(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column): str(dtype) for column, dtype in frame.dtypes.items()}


def test_empty_dataframes_preserve_contract_columns_and_dtypes(
    tmp_path: Path,
) -> None:
    with holder.open(tmp_path / "holder-data") as context:
        cards = context.cards.to_dataframe()
        complete = context.cards.to_dataframe(include_content=True)
        projects = context.projects.to_dataframe()

    assert list(cards.columns) == list(holder.CARD_METADATA_RECORD_FIELDS)
    assert _dtypes(cards) == CARD_METADATA_DTYPES
    assert list(complete.columns) == list(holder.COMPLETE_CARD_RECORD_FIELDS)
    assert _dtypes(complete) == {
        **CARD_METADATA_DTYPES,
        "content": "string",
    }
    assert list(projects.columns) == list(holder.PROJECT_RECORD_FIELDS)
    assert _dtypes(projects) == PROJECT_DTYPES


def test_card_dataframes_distinguish_unrequested_and_empty_content(
    tmp_path: Path,
) -> None:
    with holder.open(tmp_path / "holder-data") as context:
        project = context.create_project("DataFrames")
        empty = context.create_card(project.project_id, "Empty body", "")
        parent = context.create_card(project.project_id, "Parent", "parent body")
        child = context.create_card(
            project.project_id, "Child", "child body", parent.card_id
        )

        metadata = context.cards.to_dataframe()
        complete = context.cards.to_dataframe(include_content=True)
        projects = context.projects.to_dataframe()

    assert "content" not in metadata.columns
    empty_row = complete.loc[complete["card_id"] == empty.card_id].iloc[0]
    assert empty_row["content"] == ""

    parent_row = metadata.loc[metadata["card_id"] == parent.card_id].iloc[0]
    child_row = metadata.loc[metadata["card_id"] == child.card_id].iloc[0]
    assert pd.isna(parent_row["parent_card_id"])
    assert child_row["parent_card_id"] == parent.card_id
    assert metadata["deleted_at"].isna().all()
    assert pd.isna(projects.iloc[0]["git_remote_url"])
    assert pd.isna(projects.iloc[0]["project_key_id"])

    assert str(metadata["created_at"].dt.tz) == "UTC"
    assert str(metadata["updated_at"].dt.tz) == "UTC"
    assert str(projects["created_at"].dt.tz) == "UTC"
    assert parent_row["created_at"] == pd.Timestamp(
        parent.created_at, unit="s", tz="UTC"
    )
    assert projects.iloc[0]["created_at"] == pd.Timestamp(
        project.created_at, unit="s", tz="UTC"
    )
    assert _dtypes(metadata) == CARD_METADATA_DTYPES
    assert _dtypes(projects) == PROJECT_DTYPES


def test_dataframes_are_detached_and_have_no_implicit_writeback(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "holder-data"
    context = holder.open(data_dir)
    project = context.create_project("Detached")
    card = context.create_card(project.project_id, "Original", "source body")
    frame = context.cards.to_dataframe(include_content=True)
    context.close()

    frame.loc[frame["card_id"] == card.card_id, "title"] = "Edited in pandas"
    frame.loc[frame["card_id"] == card.card_id, "content"] = "local edit"
    assert frame.iloc[0]["title"] == "Edited in pandas"

    with holder.open(data_dir) as reopened:
        persisted = reopened.cards.to_dataframe(include_content=True)

    assert persisted.iloc[0]["title"] == "Original"
    assert persisted.iloc[0]["content"] == "source body"


def test_default_card_dataframe_does_not_read_authoritative_bodies(
    tmp_path: Path,
) -> None:
    with holder.open(tmp_path / "holder-data") as context:
        project = context.create_project("Metadata only")
        card = context.create_card(project.project_id, "Missing file", "body")
        (Path(project.root_path) / card.rel_path).unlink()

        metadata = context.cards.to_dataframe(project.project_id)
        assert metadata.iloc[0]["card_id"] == card.card_id
        assert "content" not in metadata.columns

        with pytest.raises(holder.HolderError, match="card content missing"):
            context.cards.to_dataframe(project.project_id, include_content=True)


@pytest.mark.parametrize("project_id", [None, "unknown-project"])
@pytest.mark.parametrize("include_content", [False, True])
def test_empty_combined_exports_preserve_all_schemas(
    tmp_path: Path, project_id: str | None, include_content: bool,
) -> None:
    with holder.open(tmp_path / "data") as context:
        tables: holder.DataFrames = context.to_dataframes(project_id, include_content=include_content)
    assert list(tables) == ["projects", "cards", "connections"]
    expected_card_dtypes = dict(CARD_METADATA_DTYPES)
    if include_content:
        expected_card_dtypes["content"] = "string"
    assert list(tables["projects"].columns) == list(holder.PROJECT_RECORD_FIELDS)
    assert list(tables["cards"].columns) == list(
        holder.COMPLETE_CARD_RECORD_FIELDS if include_content else holder.CARD_METADATA_RECORD_FIELDS
    )
    assert list(tables["connections"].columns) == list(holder.CONNECTION_RECORD_FIELDS)
    assert _dtypes(tables["projects"]) == PROJECT_DTYPES
    assert _dtypes(tables["cards"]) == expected_card_dtypes
    assert _dtypes(tables["connections"]) == CONNECTION_DTYPES
    assert all(frame.empty for frame in (tables["projects"], tables["cards"], tables["connections"]))


def test_combined_exports_match_collection_tables_and_join_after_close(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with holder.open(data) as context:
        first = context.create_project("First")
        second = context.create_project("Second")
        source = context.create_card(first.project_id, "Source", "body")
        target = context.create_card(second.project_id, "Target", "")
        context.create_card(first.project_id, "Isolated")
        context.connections.add(source.card_id, target.card_id, "references")
        tables = context.to_dataframes(include_content=True)
        pd.testing.assert_frame_equal(tables["projects"], context.projects.to_dataframe())
        pd.testing.assert_frame_equal(tables["cards"], context.cards.to_dataframe(include_content=True))
        pd.testing.assert_frame_equal(tables["connections"], context.connections.to_dataframe())

    cards = tables["cards"].merge(tables["projects"][["project_id", "name"]], on="project_id")
    assert set(cards["name"]) == {"First", "Second"}
    links = tables["connections"].merge(cards, left_on="from_card_id", right_on="card_id")
    assert links.iloc[0]["title"] == "Source"
    assert links.iloc[0]["name"] == "First"
    tables["cards"].loc[tables["cards"]["card_id"] == source.card_id, "content"] = "local edit"
    tables["connections"].loc[:, "kind"] = "local kind"
    tables["projects"].loc[:, "name"] = "local name"
    with holder.open(data) as reopened:
        assert reopened.get_card_content(source.card_id) == "body"
        assert reopened.connections.to_records()[0]["kind"] == "references"
        assert {project.name for project in reopened.list_projects()} == {"First", "Second"}


def test_combined_project_scope_preserves_external_targets(tmp_path: Path) -> None:
    with holder.open(tmp_path / "data") as context:
        first = context.create_project("First")
        second = context.create_project("Second")
        empty = context.create_project("Empty")
        source = context.create_card(first.project_id, "Source")
        target = context.create_card(second.project_id, "Target")
        context.connections.add(source.card_id, target.card_id, "references")
        context.connections.add(target.card_id, source.card_id, "references")
        scoped = context.to_dataframes(first.project_id)
        assert scoped["projects"]["project_id"].tolist() == [first.project_id]
        assert scoped["cards"]["card_id"].tolist() == [source.card_id]
        assert scoped["connections"]["from_card_id"].tolist() == [source.card_id]
        assert scoped["connections"]["to_card_id"].tolist() == [target.card_id]
        assert target.card_id not in scoped["cards"]["card_id"].tolist()
        empty_tables = context.to_dataframes(empty.project_id)
        assert empty_tables["projects"]["project_id"].tolist() == [empty.project_id]
        assert empty_tables["cards"].empty and empty_tables["connections"].empty
        missing = context.to_dataframes("missing")
        assert all(table.empty for table in (missing["projects"], missing["cards"], missing["connections"]))


def test_combined_export_reuses_card_selection_during_later_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with holder.open(tmp_path / "data") as context:
        project = context.create_project("Selection")
        original_card = context.create_card(project.project_id, "Original")
        list_cards = _native.Context.list_cards

        def changing_list_cards(native_context: _native.Context, project_id: str) -> list[dict[str, Any]]:
            selected = list_cards(native_context, project_id)
            added = context.create_card(project_id, "Added after selection")
            context.connections.add(added.card_id, original_card.card_id, "references")
            return selected

        monkeypatch.setattr(_native.Context, "list_cards", changing_list_cards)
        tables = context.to_dataframes(project.project_id)
        assert tables["cards"]["card_id"].tolist() == [original_card.card_id]
        assert tables["connections"].empty  # the later card is not a selected source


def test_combined_export_content_failures_and_closed_context(tmp_path: Path) -> None:
    with holder.open(tmp_path / "data") as context:
        project = context.create_project("Missing body")
        card = context.create_card(project.project_id, "Card", "body")
        (Path(project.root_path) / card.rel_path).unlink()
        assert "content" not in context.to_dataframes()["cards"].columns
        with pytest.raises(holder.HolderError, match="card content missing"):
            context.to_dataframes(include_content=True)
    with pytest.raises(RuntimeError, match="closed"):
        context.to_dataframes()
