"""Create, edit and reopen an independent project using temporary data."""

from pathlib import Path
from tempfile import TemporaryDirectory

import holderkit


def main() -> None:
    with TemporaryDirectory(prefix="holder-kit-workspace-") as temporary:
        path = Path(temporary) / "research"
        with holderkit.create("Research", workspace=path) as project:
            card = project.create_card("Observation", "Imported measurement")
            project.tags.add(card.card_id, "research")
            print("Saved project:", project.path)
            print("Project:", project.project_id)
            print("Initial revision:", project.revision)
        with holderkit.reopen(path) as project:
            project.update_card(card.card_id, "Reviewed measurement\n\n#research")
            records = project.cards.to_records(include_content=True)
        print("Detached records after close:", records)


if __name__ == "__main__":
    main()
