"""Create, edit and reopen an independent project using temporary data."""

from pathlib import Path
from tempfile import TemporaryDirectory

import holderkit


def main() -> None:
    with TemporaryDirectory(prefix="holder-kit-workspace-") as temporary:
        path = Path(temporary) / "research"
        with holderkit.create("Research", workspace=path) as lab:
            card = lab.context.create_card(
                lab.project.project_id, "Observation", "Imported measurement"
            )
            lab.context.tags.add(card.card_id, "research")
            print("Workspace:", lab.path)
            print("Project:", lab.project.project_id)
            print("Initial revision:", lab.revision)
        with holderkit.reopen(path) as lab:
            lab.context.update_card(card.card_id, "Reviewed measurement\n\n#research")
            records = lab.context.cards.to_records(include_content=True)
        print("Detached records after close:", records)


if __name__ == "__main__":
    main()
