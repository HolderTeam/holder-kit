"""Edit milestones, query a calendar range and join detached tables."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import holderkit


def main() -> None:
    start = int(datetime(2026, 10, 5, 9, tzinfo=timezone.utc).timestamp())
    with TemporaryDirectory(prefix="holder-milestones-") as temporary:
        with holderkit.open(Path(temporary) / "data") as context:
            project = context.create_project("Calendar")
            card = context.create_card(project.project_id, "Review evidence", "Research #review")
            milestone = context.milestones.add(
                card.card_id, start, end_at=start + 3600, kind="Appointment",
                description="Review the evidence together",
            )[0]
            updated = context.milestones.update(project.project_id, card.card_id, milestone["milestone_id"], {
                "description": "Bring notes", "end_at": None,
            })
            print("Updated:", updated)
            print("Calendar:", context.milestones.in_range(project.project_id, start, start + 86400))
            tables = context.to_dataframes(project.project_id)
        joined = tables["milestones"].merge(tables["cards"], on=["project_id", "card_id"])
        print(joined[["title", "start_at", "end_at", "all_day", "kind"]].to_string(index=False))


if __name__ == "__main__":
    main()
