from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import holderkit
from holderkit import _native


def test_cards_keep_exact_project_and_read_current_state(tmp_path: Path) -> None:
    with holderkit.create('Live', workspace=tmp_path / 'project') as project:
        card = project.create_card('Before', 'Original')
        snapshot = card.to_record()
        listed = project.cards.list()[0]
        assert card.project is project and listed.project is project
        assert listed == card and hash(listed) == hash(card)
        project.update_card(card.card_id, 'Changed', 'After')
        assert card.title == listed.title == 'After'
        assert card.content == listed.content == 'Changed'
        assert snapshot['title'] == 'Before' and snapshot['content'] == 'Original'
        updated = card.update('Final')
        assert updated.project is project and card.content == 'Final'
        project.tags.add(card.card_id, 'work')
        assert '#work' in card.content
        assert card.to_record(include_content=False)['title'] == 'After'
        identity = card.card_id
    assert card.card_id == identity and card.project is project
    assert card.project_id == project.project_id
    for read in (lambda: card.title, lambda: card.content, lambda: card.to_record(),
                 lambda: card.update('No'), card.trash, card.restore, card.purge):
        with pytest.raises(RuntimeError, match='closed'):
            read()
    assert snapshot['content'] == 'Original'


@pytest.mark.parametrize('operation', ['delete', 'trash', 'project_delete', 'project_trash'])
def test_soft_delete_aliases_promote_children_and_restore_only_parent(tmp_path: Path, operation: str) -> None:
    with holderkit.create('Tree', workspace=tmp_path / 'project') as project:
        parent = project.create_card('Parent', 'Body')
        child = project.create_card('Child', 'Child body', parent.card_id)
        grandchild = project.create_card('Grandchild', 'Grandchild body', child.card_id)
        saved = parent.to_record()
        if operation.startswith('project_'):
            getattr(project, operation.removeprefix('project_'))(parent)
        else:
            getattr(parent, operation)()
        assert parent.deleted_at is not None and parent.deleted_datetime is not None
        assert child.parent_card_id is None
        assert grandchild.parent_card_id == child.card_id
        assert parent.card_id not in {card.card_id for card in project.cards.list()}
        trashed = project.cards.trashed()
        assert len(trashed) == 1 and trashed[0].project is project and trashed[0] == parent
        assert saved['deleted_at'] is None
        assert parent.to_record(include_content=False)['deleted_at'] is not None
        with pytest.raises(ValueError, match='restore'):
            _ = parent.content
        with pytest.raises(ValueError, match='restore'):
            parent.to_record()
        restored = trashed[0].restore()
        assert restored.project is project and restored == parent
        assert parent.deleted_at is None and parent.content == 'Body'
        assert child.parent_card_id is None
        assert project.cards.trashed() == []


@pytest.mark.parametrize('operation', ['purge', 'hard_delete', 'project_purge', 'project_hard_delete'])
def test_hard_delete_requires_trash_and_invalidates_all_handles(tmp_path: Path, operation: str) -> None:
    with holderkit.create('Removal', workspace=tmp_path / 'project') as project:
        card = project.create_card('Kept', 'Body')
        alias = project.cards.list()[0]
        def remove() -> None:
            if operation == 'purge':
                card.purge()
            elif operation == 'hard_delete':
                card.delete(hard=True)
            elif operation == 'project_purge':
                project.purge(card)
            else:
                project.delete(card, hard=True)
        with pytest.raises(holderkit.HolderError):
            remove()
        assert card.content == 'Body'
        card.trash()
        trash_path = next((Path(project.root_path) / "trash").rglob(f"{card.card_id}.md"))
        assert trash_path.exists()
        remove()
        assert not trash_path.exists() and project.cards.trashed() == []
        assert card.card_id == alias.card_id and card.project is project
        # Core reference resolution also accepts titles. A stale handle must never
        # resolve a different card whose title happens to match the removed ID.
        decoy = project.create_card(card.card_id, 'Do not touch')
        for handle in (card, alias):
            for action in (lambda: handle.title, lambda: handle.to_record(), handle.restore, handle.trash):
                with pytest.raises(KeyError, match='Card not found'):
                    action()
        assert decoy.content == 'Do not touch'


def test_project_operations_reject_foreign_cards_and_non_cards(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / 'context') as context:
        first = context.create_project('First')
        second = context.create_project('Second')
        card = second.create_card('Foreign', 'Body')
        for operation in (first.trash, first.delete, first.restore, first.purge):
            with pytest.raises(ValueError, match='does not belong'):
                operation(card)
            with pytest.raises(TypeError, match='Card'):
                operation(card.card_id)  # type: ignore[arg-type]
        assert card.content == 'Body' and card.deleted_at is None
        # Same identities in a different context are not interchangeable handles.
        with holderkit.open(tmp_path / 'other') as other:
            forged = holderkit.Card(holderkit.Project(other._context, second.project_id), card.card_id)
            with pytest.raises(ValueError, match='does not belong'):
                second.trash(forged)
        second.close()
        with pytest.raises(RuntimeError, match='closed'):
            second.trash(card)


def test_context_cards_borrow_project_and_follow_context_lifetime(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / 'context') as context:
        project = context.create_project('Context')
        card = context.create_card(project.project_id, 'Card', 'Body')
        assert card.project.project_id == project.project_id
        assert card.project._context is context._context
        listed = context.cards.list()[0]
        listed.project.close()
        assert not context.closed and not card.project.closed
        updated = context.update_card(card.card_id, 'Changed')
        assert updated.project.project_id == project.project_id and card.content == 'Changed'
        card.trash()
        project.restore(card)
        assert card.deleted_at is None
    with pytest.raises(RuntimeError, match='closed'):
        _ = card.title


def test_find_and_restore_trash_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / 'project'
    with holderkit.create('Reopen', workspace=path) as project:
        card = project.create_card('Saved', 'Retained body')
        card.trash()
    with holderkit.reopen(path) as project:
        cards = project.cards.trashed()
        assert len(cards) == 1 and cards[0].project is project
        restored = project.restore(cards[0])
        assert restored.card_id == card.card_id and restored.content == 'Retained body'


def test_restore_uses_reachable_parent_and_does_not_restore_children(tmp_path: Path) -> None:
    with holderkit.create('Ancestors', workspace=tmp_path / 'project') as project:
        parent = project.create_card('Parent', '')
        child = project.create_card('Child', '', parent.card_id)
        child.trash()
        parent.trash()
        restored = child.restore()
        assert restored.parent_card_id is None
        assert parent.deleted_at is not None
        with pytest.raises(holderkit.HolderError):
            restored.restore()
        with pytest.raises(holderkit.HolderError):
            parent.trash()


def test_metadata_properties_do_not_read_files_or_unbounded_lists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with holderkit.create('Metadata', workspace=tmp_path / 'project') as project:
        card = project.create_card('Card', 'Body')
        (Path(project.root_path) / card.rel_path).unlink()
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError('Live metadata read must not read bodies or whole collections')
        monkeypatch.setattr(_native.Context, 'list_cards', forbidden)
        assert card.title == 'Card'
        assert card.to_record(include_content=False)['title'] == 'Card'
        with pytest.raises(holderkit.HolderError, match='missing'):
            _ = card.content


def test_lifecycle_validation_and_native_closed_errors(tmp_path: Path) -> None:
    with holderkit.create('Validation', workspace=tmp_path / 'project') as project:
        card = project.create_card('Card', '')
        with pytest.raises(TypeError):
            card.delete(True)  # type: ignore[call-arg]
        for value in (1, 'true', None):
            with pytest.raises(TypeError, match='bool'):
                card.delete(hard=value)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match='bool'):
            card.to_record(include_content=1)  # type: ignore[call-overload]
        native = project._live_context()
    for operation in (native.trash_card, native.restore_card, native.purge_card):
        with pytest.raises(RuntimeError, match='closed'):
            operation(card.card_id)
    with pytest.raises(RuntimeError, match='closed'):
        native.resolve_card(project.project_id, card.card_id)
    with pytest.raises(RuntimeError, match='closed'):
        native.list_trashed_cards(project.project_id)
