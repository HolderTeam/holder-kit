"""Work with a live Card, then trash, restore and permanently remove it."""

from __future__ import annotations

import json

import holderkit


def main() -> None:
    with holderkit.create("Python card example") as project:
        card = project.create_card("Hello from Python", "Initial body")
        assert card.project is project
        saved = card.to_record()
        card.update("Updated findings", title="Updated from Python")
        print("Current:", json.dumps(card.to_record(), indent=2))
        print("Earlier:", json.dumps(saved, indent=2))

        card.trash()  # card.delete() is equivalent
        print("Trash:", [item.title for item in project.cards.trashed()])
        card = card.restore()
        print("Restored:", card.content)

        card.delete()
        card.purge()  # card.delete(hard=True) is equivalent
        print("Remaining cards:", len(project.cards.list()))
    # Closing retains the project and its history.


if __name__ == "__main__":
    main()
