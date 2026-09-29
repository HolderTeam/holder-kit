from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import holder


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
