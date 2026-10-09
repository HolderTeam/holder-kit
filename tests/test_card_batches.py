from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import holderkit
from holderkit import _native


@pytest.mark.parametrize("include_content", [False, True])
@pytest.mark.parametrize("count,batch_size,lengths", [(0, 2, []), (1, 2, [1]), (5, 2, [2, 2, 1]), (6, 2, [2, 2, 2])])
def test_batches_have_detached_records_and_correct_sizes(
    tmp_path: Path, include_content: bool, count: int, batch_size: int, lengths: list[int],
) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Selected")
        other = context.create_project("Other")
        other.create_card("Excluded", "Other project")
        cards = [project.create_card(str(i), f"Body {i}") for i in range(count)]
        batches = list(project.cards(batch_size=batch_size, include_content=include_content))
        assert [len(batch) for batch in batches] == lengths
        records = [record for batch in batches for record in batch]
        assert {record["card_id"] for record in records} == {card.card_id for card in cards}
        fields = holderkit.COMPLETE_CARD_RECORD_FIELDS if include_content else holderkit.CARD_METADATA_RECORD_FIELDS
        assert all(set(record) == set(fields) for record in records)
        assert all(record["project_id"] == project.project_id for record in records)
        expected = project.cards.to_records(include_content=True) if include_content else project.cards.to_records()
        assert sorted(records, key=lambda record: record["card_id"]) == sorted(expected, key=lambda record: record["card_id"])
        if include_content:
            assert [record["card_id"] for record in records] == sorted(record["card_id"] for record in records)
        else:
            assert [(record["updated_at"], record["card_id"]) for record in records] == sorted(
                ((record["updated_at"], record["card_id"]) for record in records), reverse=True,
            )
    # Returned values own no context; modifying them does not alter saved data.
    if records:
        records[0]["title"] = "Detached edit"
        with holderkit.open(tmp_path / "data") as reopened:
            assert all(card.title != "Detached edit" for card in reopened.list_cards(project.project_id))


@pytest.mark.parametrize("include_content", [False, True])
def test_batches_are_lazy_and_do_not_use_unbounded_lists(
    tmp_path: Path, include_content: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with holderkit.create("Lazy", workspace=tmp_path / "project") as project:
        for index in range(5):
            project.create_card(str(index), str(index))
        original_complete = _native.Context.list_complete_cards_page
        original_query = _native.Context.query_cards
        calls: list[int] = []
        def complete(self: _native.Context, project_id: str, cursor: str | None = None, limit: int = 256) -> dict[str, Any]:
            calls.append(limit)
            return original_complete(self, project_id, cursor, limit)
        def query(self: _native.Context, project_id: str, request_json: str) -> dict[str, Any]:
            calls.append(json.loads(request_json)["limit"])
            return original_query(self, project_id, request_json)
        def unbounded(self: _native.Context, project_id: str) -> list[dict[str, Any]]:
            raise AssertionError("Batch iteration used an unbounded list")
        monkeypatch.setattr(_native.Context, "list_complete_cards_page", complete)
        monkeypatch.setattr(_native.Context, "query_cards", query)
        monkeypatch.setattr(_native.Context, "list_cards", unbounded)
        batches = project.cards(batch_size=2, include_content=include_content)
        assert calls == []
        assert len(next(batches)) == 2
        assert calls == [2]
        # Dropping an iterator neither fetches further pages nor closes the project.
        del batches
        assert calls == [2] and not project.closed


@pytest.mark.parametrize("include_content", [False, True])
def test_user_batches_can_span_native_pages(
    tmp_path: Path, include_content: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_native, "CARD_PAGE_MAX_LIMIT", 2)
    with holderkit.create("Pages", workspace=tmp_path / "project") as project:
        for index in range(7):
            project.create_card(str(index), "Body")
        batches = list(project.cards(batch_size=3, include_content=include_content))
        assert [len(batch) for batch in batches] == [3, 3, 1]
        assert len({record["card_id"] for batch in batches for record in batch}) == 7


def test_metadata_batches_do_not_read_card_files_and_complete_page_failure_propagates(tmp_path: Path) -> None:
    with holderkit.create("Files", workspace=tmp_path / "project") as project:
        cards = [project.create_card(str(i), f"Body {i}") for i in range(4)]
        selected = sorted(cards, key=lambda card: card.card_id)[2]
        (Path(project.root_path) / selected.rel_path).unlink()
        assert sum(len(batch) for batch in project.cards(batch_size=2)) == 4
        batches = project.cards(batch_size=2, include_content=True)
        assert len(next(batches)) == 2
        with pytest.raises(holderkit.HolderError):
            next(batches)


@pytest.mark.parametrize("include_content", [False, True])
def test_closing_project_invalidates_unread_and_buffered_batches(
    tmp_path: Path, include_content: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_native, "CARD_PAGE_MAX_LIMIT", 2)
    project = holderkit.create("Close", workspace=tmp_path / "project")
    for index in range(4):
        project.create_card(str(index), "Body")
    unread = project.cards(batch_size=2, include_content=include_content)
    buffered = project.cards(batch_size=3, include_content=include_content)
    detached = next(buffered)
    project.close()
    assert len(detached) == 3
    for iterator in (unread, buffered):
        with pytest.raises(RuntimeError, match="closed"):
            next(iterator)


@pytest.mark.parametrize("size,error", [(0, ValueError), (-1, ValueError), (True, TypeError), (1.5, TypeError), ("2", TypeError), (None, TypeError)])
def test_batch_size_validation_is_immediate(tmp_path: Path, size: Any, error: type[Exception]) -> None:
    with holderkit.create("Validation", workspace=tmp_path / "project") as project:
        with pytest.raises(error, match="positive integer"):
            project.cards(batch_size=size)
        with pytest.raises(TypeError, match="bool"):
            project.cards(include_content=1)  # type: ignore[call-overload]


def test_native_query_propagates_invalid_request_and_closed_errors(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Query")
        with pytest.raises(ValueError):
            context._context.query_cards(project.project_id, '{"view":"recent","limit":0}')
        native = context._context
    with pytest.raises(RuntimeError, match="closed"):
        native.query_cards(project.project_id, '{"view":"recent","limit":2}')


collection_support = pytest.mark.skipif(
    not _native.CARD_COLLECTION_SUPPORTED, reason="Requires Core collection pagination SDK",
)


@collection_support
@pytest.mark.parametrize("include_content", [False, True])
@pytest.mark.parametrize("order", [None, "card_id", "updated"])
def test_filtered_batches_combine_tags_and_hierarchy(
    tmp_path: Path, include_content: bool, order: Any,
) -> None:
    with holderkit.open(tmp_path / "data") as context:
        project = context.create_project("Selected")
        other = context.create_project("Other")
        foreign = other.create_card("Foreign", "#work")
        parent = project.create_card("Parent", "#work")
        sibling = project.create_card("Sibling", "#work")
        children = [project.create_card(str(i), "Body #work", parent.card_id) for i in range(5)]
        excluded = project.create_card("Excluded", "#other", parent.card_id)
        grandchild = project.create_card("Grandchild", "#work", children[0].card_id)
        # Content reads must not visit an excluded card's missing file.
        (Path(project.root_path) / excluded.rel_path).unlink()
        batches = list(project.cards(
            tag="WORK", parent_card_id=parent.card_id, batch_size=2,
            include_content=include_content, order=order,
        ))
        assert [len(batch) for batch in batches] == [2, 2, 1]
        records = [record for batch in batches for record in batch]
        assert {record["card_id"] for record in records} == {card.card_id for card in children}
        actual = [(record["updated_at"], record["card_id"]) for record in records]
        if order == "updated" or (order is None and not include_content):
            assert actual == sorted(actual, reverse=True)
        else:
            assert [record["card_id"] for record in records] == sorted(card.card_id for card in children)
        fields = holderkit.COMPLETE_CARD_RECORD_FIELDS if include_content else holderkit.CARD_METADATA_RECORD_FIELDS
        assert all(set(record) == set(fields) for record in records)
        if include_content:
            assert all(record.get("content") == "Body #work" for record in records)
        roots = [record for batch in project.cards(tag="work", roots=True) for record in batch]
        assert {record["card_id"] for record in roots} == {parent.card_id, sibling.card_id}
        all_tagged = [record for batch in project.cards(tag="work") for record in batch]
        assert {record["card_id"] for record in all_tagged} == {
            parent.card_id, sibling.card_id, grandchild.card_id, *(card.card_id for card in children),
        }
        assert list(project.cards(tag="missing")) == []
        assert list(project.cards(parent_card_id=foreign.card_id)) == []


@collection_support
@pytest.mark.parametrize("include_content", [False, True])
def test_filtered_batches_are_lazy_bounded_and_invalidated_on_close(
    tmp_path: Path, include_content: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = holderkit.create("Filtered", workspace=tmp_path / "project")
    for i in range(5):
        project.create_card(str(i), "#work")
    original = _native.Context.collection_cards_page
    calls: list[dict[str, Any]] = []
    def page(self: _native.Context, project_id: str, request_json: str) -> dict[str, Any]:
        calls.append(json.loads(request_json))
        return original(self, project_id, request_json)
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Filtered batches must use Core collection pagination")
    monkeypatch.setattr(_native.Context, "collection_cards_page", page)
    monkeypatch.setattr(_native.Context, "list_cards", forbidden)
    monkeypatch.setattr(_native.Context, "query_cards", forbidden)
    monkeypatch.setattr(_native.Context, "get_card_content", forbidden)
    monkeypatch.setattr(_native, "CARD_PAGE_MAX_LIMIT", 2)
    iterator = project.cards(tag="work", include_content=include_content, batch_size=3)
    assert calls == []
    returned = next(iterator)
    assert len(returned) == 3
    assert len(calls) == 2
    assert all(request["limit"] == 2 and request["tag"] == "work" for request in calls)
    assert "cursor" not in calls[0] and calls[1]["cursor"] is not None
    project.close()
    with pytest.raises(RuntimeError, match="closed"):
        next(iterator)
    assert len(calls) == 2
    assert len(returned) == 3


@collection_support
def test_filtered_metadata_avoids_files_and_body_errors_propagate(tmp_path: Path) -> None:
    with holderkit.create("Files", workspace=tmp_path / "project") as project:
        card = project.create_card("Missing", "#work")
        (Path(project.root_path) / card.rel_path).unlink()
        assert sum(len(batch) for batch in project.cards(tag="work")) == 1
        with pytest.raises(holderkit.HolderError):
            list(project.cards(tag="work", include_content=True))
        with pytest.raises(ValueError):
            list(project.cards(tag="#work"))
        with pytest.raises(ValueError):
            project._live_context().collection_cards_page(project.project_id, '{"limit":0}')


@pytest.mark.parametrize("options,error", [
    ({"roots":1}, TypeError), ({"roots":True,"parent_card_id":"a"}, ValueError),
    ({"tag":1}, TypeError), ({"tag":""}, ValueError),
    ({"parent_card_id":1}, TypeError), ({"parent_card_id":""}, ValueError),
    ({"order":"title"}, ValueError),
])
def test_filter_argument_validation_is_immediate(tmp_path: Path, options: Any, error: type[Exception]) -> None:
    with holderkit.create("Validation", workspace=tmp_path / "project") as project:
        with pytest.raises(error):
            project.cards(**options)


def test_old_sdk_refuses_filters_but_keeps_existing_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_native, "CARD_COLLECTION_SUPPORTED", 0)
    with holderkit.create("Old SDK", workspace=tmp_path / "project") as project:
        project.create_card("Card", "#work")
        assert len(list(project.cards())) == 1
        with pytest.raises(NotImplementedError, match="Core SDK"):
            project.cards(tag="work")
