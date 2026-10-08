"""Create a research project, add a card and export its data."""

import holderkit


def main() -> None:
    with holderkit.create("Research") as project:
        card = project.create_card("Observation", "Measurements from Python")
        project.tags.add(card.card_id, "research")
        records = project.cards.to_records(include_content=True)
    for record in records:
        print(record["title"], record["content"])


if __name__ == "__main__":
    main()
