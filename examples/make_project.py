"""Create a research project, add a card and export its data."""

import holderkit


def main() -> None:
    with holderkit.create("Research") as lab:
        card = lab.context.create_card(
            lab.project.project_id, "Observation", "Measurements from Python"
        )
        lab.context.tags.add(card.card_id, "research")
        records = lab.context.cards.to_records(include_content=True)
    for record in records:
        print(record["title"], record["content"])


if __name__ == "__main__":
    main()
