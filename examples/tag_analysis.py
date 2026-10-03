"""Use semantic tag operations and join detached membership tables."""

from pathlib import Path
from tempfile import TemporaryDirectory

import holder


def main() -> None:
    with TemporaryDirectory(prefix="holder-tags-") as temporary:
        with holder.open(Path(temporary) / "data") as context:
            project = context.create_project("Tagged notes")
            card = context.create_card(project.project_id, "Evidence", "Review #evidence in prose.")
            print("Add todo:", context.tags.add(card.card_id, "TODO").name)
            print("Remove prose tag:", context.tags.remove(card.card_id, "evidence").name)
            print("Counts:", context.tags.project_counts(project.project_id))
            print("Todo cards:", context.tags.cards_with_tag(project.project_id, "TODO"))
            tables = context.to_dataframes(project.project_id)
        # The context is closed; these tables have no native lifetime or write-back.
        joined = tables["tags"].merge(tables["cards"], on=["project_id", "card_id"])
        print(joined[["title", "tag", "editable"]].to_string(index=False))


if __name__ == "__main__":
    main()
