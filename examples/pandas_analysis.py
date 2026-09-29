"""Run ordinary pandas analysis over detached Holder card data."""

from __future__ import annotations

import tempfile
from pathlib import Path

import holder


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="holder-python-pandas-") as temporary:
        with holder.open(Path(temporary) / "data") as context:
            research = context.create_project("Research")
            journal = context.create_project("Journal")
            context.create_card(research.project_id, "Pandas notes", "tabular data")
            context.create_card(research.project_id, "Empty draft", "")
            context.create_card(journal.project_id, "Daily note", "small progress")

            projects = context.projects.to_dataframe()
            cards = context.cards.to_dataframe(include_content=True)

        # Everything below operates on detached pandas data after Holder is closed.
        analysis = cards.assign(content_length=cards["content"].str.len()).merge(
            projects[["project_id", "name"]], on="project_id"
        )
        non_empty = analysis.loc[analysis["content_length"] > 0]
        totals = analysis.groupby("name", as_index=False)["content_length"].sum()

        print("Non-empty cards:")
        print(non_empty[["name", "title", "content_length"]].to_string(index=False))
        print("\nContent length by project:")
        print(totals.to_string(index=False))


if __name__ == "__main__":
    main()
