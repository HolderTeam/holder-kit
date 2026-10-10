from __future__ import annotations

from pathlib import Path

import pytest

import holderkit


def test_moves_follow_current_hierarchy_and_keep_records_detached(tmp_path: Path) -> None:
    with holderkit.create('Tree', workspace=tmp_path / 'project') as project:
        parent = project.create_card('Parent', 'Parent body')
        first = project.create_card('First', '', parent.card_id)
        second = project.create_card('Second', '', parent.card_id)
        card = project.create_card('Moved', 'Retained body')
        child = project.create_card('Child', '', card.card_id)
        alias = next(c for c in project.cards.list() if c == card)
        snapshot = card.to_record()
        assert card.parent is None
        assert card.move(into=parent) is card
        current_parent = card.parent
        assert current_parent is not None and current_parent == alias.parent == parent
        assert current_parent.project is project
        parent.update('Parent body', 'Renamed parent')
        assert current_parent.title == 'Renamed parent'
        assert snapshot['parent_card_id'] is None
        assert child.parent == card
        assert card.sort_key > max(first.sort_key, second.sort_key)
        card.move(before=first)
        assert card.sort_key < first.sort_key
        card.move(after=first)
        assert first.sort_key < card.sort_key < second.sort_key
        card.move(before=parent)
        assert card.parent is alias.parent is None
        assert card.sort_key < parent.sort_key
        card.move(after=parent)
        assert card.sort_key > parent.sort_key
        assert card.content == snapshot['content'] == 'Retained body'
        assert snapshot['parent_card_id'] is None
        card.move(into=parent)
        parent.trash()
        assert card.parent is None
        assert child.parent == card
        parent.restore()
        assert card.parent is None
    with holderkit.reopen(tmp_path / 'project') as reopened:
        moved = next(c for c in reopened.cards.list() if c.card_id == card.card_id)
        assert moved.parent is None
        nested = next(c for c in reopened.cards.list() if c.card_id == child.card_id)
        assert nested.parent == moved and nested.parent.project is reopened


def test_core_rejects_cycles_and_self_placement_without_mutation(tmp_path: Path) -> None:
    with holderkit.create('Cycles', workspace=tmp_path / 'project') as project:
        parent = project.create_card('Parent')
        child = project.create_card('Child', parent_card_id=parent.card_id)
        before = project.cards.to_records()
        for options in ({'into':child}, {'before':child}, {'after':child},
                        {'into':parent}, {'before':parent}, {'after':parent}):
            with pytest.raises(holderkit.HolderError):
                parent.move(**options)
            assert project.cards.to_records() == before


def test_moves_validate_options_and_owners(tmp_path: Path) -> None:
    with holderkit.open(tmp_path / 'data') as context:
        project = context.create_project('Tree')
        other = context.create_project('Other')
        card = project.create_card('Card')
        target = project.create_card('Target')
        foreign = other.create_card('Foreign')
        for options in ({}, {'into':None}, {'before':target, 'after':target},
                        {'into':target, 'before':target}):
            with pytest.raises(ValueError, match='exactly one'):
                card.move(**options)
        with pytest.raises(TypeError, match='Card'):
            card.move(into=target.card_id)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match='project'):
            card.move(into=foreign)
        with holderkit.create('Separate', workspace=tmp_path / 'separate') as separate:
            forged = holderkit.Card(separate, target.card_id)
            with pytest.raises(ValueError, match='project'):
                card.move(into=forged)
        borrowed = context.cards.list(project.project_id)
        borrowed_target = next(c for c in borrowed if c == target)
        card.move(into=borrowed_target)
        assert card.parent == target
        borrowed_target.project.close()
        with pytest.raises(RuntimeError, match='closed'):
            card.move(before=borrowed_target)
        assert card.parent == target


def test_movement_and_parent_reads_follow_lifecycle(tmp_path: Path) -> None:
    with holderkit.create('Lifecycle', workspace=tmp_path / 'project') as project:
        card = project.create_card('Card')
        target = project.create_card('Target')
        target.trash()
        with pytest.raises(ValueError, match='live cards'):
            card.move(into=target)
        target.restore()
        card.trash()
        with pytest.raises(ValueError, match='live cards'):
            card.move(before=target)
        card.restore().move(into=target)
        assert card.parent == target
        card.trash()
        card.purge()
        project.create_card(card.card_id, 'Decoy')
        with pytest.raises(KeyError):
            _ = card.parent
        with pytest.raises(KeyError):
            card.move(into=target)
        with pytest.raises(KeyError):
            target.move(after=card)
    with pytest.raises(RuntimeError, match='closed'):
        _ = target.parent
    with pytest.raises(RuntimeError, match='closed'):
        target.move(into=target)
