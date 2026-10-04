"""Export typed records and use them after the native context closes."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from holderkit import Context


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="holder-kit-records-") as temporary:
        with Context(Path(temporary) / "data") as context:
            project = context.create_project("Detached records")
            context.create_card(project.project_id, "First", "A complete body")
            context.create_card(project.project_id, "Second", "Another body")
            records = context.cards.to_records(
                project.project_id, include_content=True
            )

        # These dictionaries contain no pointers or references to the closed context.
        print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
