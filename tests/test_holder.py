from __future__ import annotations

import gc
import json
from dataclasses import FrozenInstanceError
from datetime import timezone
from pathlib import Path

import pytest

import holder
from holder import _native
from holder.data.card import Card as DomainCard
from holder.data.card import CardMetadataRecord as DomainCardMetadataRecord
from holder.data.card import CardRecord as DomainCardRecord
from holder.data.card import CompleteCardRecord as DomainCompleteCardRecord
from holder.data.project import Project as DomainProject
from holder.data.project import ProjectRecord as DomainProjectRecord


def test_native_extension_imports() -> None:
    assert _native.__name__ == "holder._native"
    assert issubclass(holder.HolderError, RuntimeError)


def test_domain_data_types_are_reexported() -> None:
    assert holder.Card is DomainCard
    assert holder.CardMetadataRecord is DomainCardMetadataRecord
    assert holder.CardRecord is DomainCardRecord
    assert holder.CompleteCardRecord is DomainCompleteCardRecord
    assert holder.Project is DomainProject
    assert holder.ProjectRecord is DomainProjectRecord


def test_complete_card_lifecycle(tmp_path: Path) -> None:
    with holder.Context(tmp_path / "holder-data") as context:
        project = context.create_project("Python test")
        card = context.create_card(
            project.project_id, "First card", "Initial body"
        )

        assert context.get_card_content(card.card_id) == "Initial body"
        assert context.list_cards(project.project_id) == [card]

        updated = context.update_card(
            card.card_id, "Updated body", title="Updated card"
        )
        assert updated.card_id == card.card_id
        assert updated.title == "Updated card"
        assert context.get_card_content(card.card_id) == "Updated body"
        assert context.list_cards(project.project_id)[0].title == "Updated card"

    assert context.closed


def test_invalid_input_and_native_failures(tmp_path: Path) -> None:
    context = holder.Context(tmp_path / "holder-data")

    with pytest.raises(ValueError, match="name"):
        context.create_project("")

    with pytest.raises(holder.HolderError, match="project not found"):
        context.create_card("missing-project", "Card")

    context.close()
    context.close()
    with pytest.raises(RuntimeError, match="closed"):
        context.list_cards("anything")


def test_context_destruction_releases_native_resources(tmp_path: Path) -> None:
    data_dir = tmp_path / "holder-data"
    for _ in range(20):
        context = holder.Context(data_dir)
        context.close()

    context = holder.Context(data_dir)
    del context
    gc.collect()

    with holder.Context(data_dir) as reopened:
        project = reopened.create_project("Reopened")
        assert project.name == "Reopened"


def test_failed_context_initialization_releases_partial_state(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "not-a-directory"
    not_a_directory.write_text("occupied", encoding="utf-8")

    with pytest.raises(holder.HolderError):
        holder.Context(not_a_directory)

    with holder.Context(tmp_path / "valid-data") as context:
        assert context.create_project("Still usable").name == "Still usable"


def test_context_keeps_working_after_result_objects_are_released(tmp_path: Path) -> None:
    context = holder.Context(tmp_path / "holder-data")
    project = context.create_project("Ownership")
    project_id = project.project_id
    del project
    gc.collect()

    card = context.create_card(project_id, "Independent result", "body")
    card_id = card.card_id
    del card
    gc.collect()

    assert context.get_card_content(card_id) == "body"
    context.close()


def test_type_validation(tmp_path: Path) -> None:
    context = holder.Context(tmp_path / "holder-data")
    with pytest.raises(TypeError):
        context.create_project(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="embedded null"):
        context.create_project("bad\x00name")
    context.close()


def test_typed_collections_and_records_are_detached(tmp_path: Path) -> None:
    context = holder.Context(tmp_path / "holder-data")
    first_project = context.create_project("First")
    second_project = context.create_project("Second")
    parent = context.create_card(first_project.project_id, "Parent", "parent body")
    context.create_card(
        first_project.project_id, "Child", "child body", parent.card_id
    )
    context.create_card(second_project.project_id, "Other", "other body")

    projects = context.projects.list()
    cards = context.cards.list()
    project_records = context.projects.to_records()
    metadata_records: list[holder.CardMetadataRecord] = context.cards.to_records(
        first_project.project_id
    )
    complete_records: list[holder.CompleteCardRecord] = context.cards.to_records(
        first_project.project_id, include_content=True
    )
    context.close()

    assert {project.name for project in projects} == {"First", "Second"}
    assert {card.content for card in cards} == {
        "parent body",
        "child body",
        "other body",
    }
    assert {record["name"] for record in project_records} == {"First", "Second"}
    assert all("content" not in record for record in metadata_records)
    assert {record["content"] for record in complete_records} == {
        "parent body",
        "child body",
    }
    child_record = next(
        record for record in complete_records if record["title"] == "Child"
    )
    assert child_record["parent_card_id"] == parent.card_id
    assert json.loads(json.dumps(metadata_records)) == metadata_records
    assert json.loads(json.dumps(complete_records)) == complete_records


def test_record_contracts_have_stable_fields_and_empty_results(tmp_path: Path) -> None:
    with holder.Context(tmp_path / "holder-data") as context:
        assert context.projects.to_records() == []
        assert context.cards.to_records() == []
        assert context.cards.to_records(include_content=True) == []

        project = context.create_project("Contracts")
        card = context.create_card(project.project_id, "Typed", "body")

        assert tuple(project.to_record()) == holder.PROJECT_RECORD_FIELDS
        assert tuple(card.to_record()) == holder.CARD_RECORD_FIELDS
        assert tuple(card.to_record()) == holder.COMPLETE_CARD_RECORD_FIELDS
        metadata = context.cards.to_records(project.project_id)[0]
        assert tuple(metadata) == holder.CARD_METADATA_RECORD_FIELDS
        assert "content" not in metadata
        assert project.created_datetime.tzinfo is timezone.utc
        assert card.updated_datetime.tzinfo is timezone.utc
        assert card.deleted_datetime is None

        with pytest.raises(FrozenInstanceError):
            card.title = "mutation"  # type: ignore[misc]


def test_native_complete_card_pages_use_opaque_lookahead_cursor(
    tmp_path: Path,
) -> None:
    with holder.Context(tmp_path / "holder-data") as context:
        project = context.create_project("Pagination")
        first = context.create_card(project.project_id, "One", "first body")
        second = context.create_card(project.project_id, "Two", "second body")
        expected = {
            first.card_id: first.content,
            second.card_id: second.content,
        }

        first_page = context._context.list_complete_cards_page(
            project.project_id, limit=1
        )
        assert len(first_page["cards"]) == 1
        first_card = first_page["cards"][0]
        assert first_card["content"] == expected[first_card["card_id"]]
        assert first_page["next_cursor"] == first_card["card_id"]

        second_page = context._context.list_complete_cards_page(
            project.project_id, first_page["next_cursor"], 1
        )
        assert len(second_page["cards"]) == 1
        second_card = second_page["cards"][0]
        assert second_card["content"] == expected[second_card["card_id"]]
        assert second_page["next_cursor"] is None
        assert first_card["card_id"] != second_card["card_id"]

        with pytest.raises(ValueError, match="limit"):
            context._context.list_complete_cards_page(project.project_id, limit=0)
        with pytest.raises(ValueError, match="limit"):
            context._context.list_complete_cards_page(project.project_id, limit=1001)


def test_metadata_records_do_not_require_card_files(tmp_path: Path) -> None:
    with holder.Context(tmp_path / "holder-data") as context:
        project = context.create_project("Metadata only")
        card = context.create_card(project.project_id, "Missing body", "body")
        (Path(project.root_path) / card.rel_path).unlink()

        records = context.cards.to_records(project.project_id)
        assert [record["card_id"] for record in records] == [card.card_id]
        assert "content" not in records[0]

        with pytest.raises(holder.HolderError, match="card content missing"):
            context.cards.to_records(project.project_id, include_content=True)
