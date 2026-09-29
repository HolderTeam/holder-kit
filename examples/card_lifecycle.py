"""Create, retrieve, and update a card using embedded libholder."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from holder import Context


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="holder-python-example-") as temporary:
        data_dir = Path(temporary) / "data"
        with Context(data_dir) as context:
            project = context.create_project("Python example")
            card = context.create_card(
                project["project_id"], "Hello from Python", "Initial body"
            )
            print("Created:", json.dumps(card, indent=2))
            print("Retrieved body:", context.get_card_content(card["card_id"]))

            updated = context.update_card(
                card["card_id"], "Updated through libholder", "Updated from Python"
            )
            print("Updated:", json.dumps(updated, indent=2))
            print("Cards:", json.dumps(context.list_cards(project["project_id"]), indent=2))


if __name__ == "__main__":
    main()
