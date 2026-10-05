# Holder Kit

**Analyse, transform and import Holder data with Python.**

Holder Kit is a Python toolkit for working directly with Holder data outside any running Holder application.

It is intended for data-oriented and offline workloads:
* analysing a knowledge base,
* bulk importing or transforming cards,
* preparing datasets, machine learning, notebooks, experiments,
* building graphs,
* and connecting Holder data to the wider Python scientific ecosystem.

Holder Kit runs `libholder` directly inside the Python process.
It does not communicate with a running Holder daemon and is not intended
to be the general-purpose Python interface for controlling a live Holder installation.

## What can you do with it?

Holder Kit gives Python programs direct access to Holder projects, cards, connections, tags and milestones.

Typical uses include:

- **Data analysis** — load Holder data into pandas and explore it with familiar Python tools.
- **Bulk import and transformation** — create or modify large collections of cards programmatically.
- **Machine learning** — extract Holder content for classification, clustering, embeddings, ranking and other experiments.
- **Graph analysis** — export explicit connections between cards to NetworkX.
- **Dataset and corpus preparation** — turn a Holder knowledge base into structured Python records for further processing.
- **Offline automation** — perform maintenance, migration and batch operations without running the Holder daemon.

The base package exposes ordinary Python records and has no data-science dependencies. pandas and NetworkX integrations are available as optional extras.

## A first example

```python
import holderkit

with holderkit.open("./knowledge") as holder:
    project = holder.create_project("Research")

    card = holder.create_card(
        project.project_id,
        "Interesting question",
        "Something worth investigating.",
    )

    print(card.title)
```

A Holder context can also expose existing cards as ordinary Python records:

```python
import holderkit

with holderkit.open("./knowledge") as holder:
    cards = holder.cards.to_records(include_content=True)

for card in cards:
    print(card["title"])
```

The returned records are detached from Holder, so they remain ordinary Python data after the context has closed.

## Analyse Holder with pandas

Install the pandas integration to turn Holder data into DataFrames:

```python
import holderkit

with holderkit.open("./knowledge") as holder:
    tables = holder.to_dataframes(include_content=True)

cards = tables["cards"]
projects = tables["projects"]

cards_with_projects = cards.merge(
    projects[["project_id", "name"]],
    on="project_id",
)
```

`to_dataframes()` provides tables for projects, cards, connections, tags and milestones.

Editing a DataFrame does not modify Holder. Exports are detached data intended for analysis and integration with the wider Python ecosystem.

## Explore connections with NetworkX

Holder cards can have explicit typed connections to other cards.

```python
import holderkit

with holderkit.open("./knowledge") as holder:
    graph = holder.to_networkx()
```

The result is a NetworkX `MultiDiGraph`, making it possible to apply existing graph algorithms and visualisation tools to relationships in your Holder knowledge.

## Tags and milestones

Tags and milestones are first-class parts of the Holder API:

```python
with holderkit.open("./knowledge") as holder:
    project = holder.create_project("Research")
    card = holder.create_card(project.project_id, "Read paper")

    holder.tags.add(card.card_id, "todo")
    holder.milestones.add(card.card_id, 1791190800)
```

They can also be exported alongside cards, projects and connections for analysis.

## Installation

Holder Kit is currently in early development.

The Python distribution is named `holder-kit` and the import package is `holderkit`.

See [Building Holder Kit](docs/building.md) for installing the current version from source.

Ubuntu packages are also available as `python3-holder-kit` for supported Holder package repositories.

## How Holder Kit fits into Holder

Holder Kit is a Python binding over `libholder`.

It runs Holder directly inside the Python process rather than communicating with `holderd` over the Framework API. This makes it suitable for scripts, notebooks, data analysis and applications that want to embed Holder functionality.

Holder Kit is versioned independently from the Holder Framework and core library.

## Examples

The repository includes examples covering:

- card creation and lifecycle;
- detached Python records;
- pandas analysis;
- connection graphs;
- tag analysis;
- milestone and calendar analysis.

See the [`examples/`](examples/) directory.

## Documentation

- [Detached record contracts](docs/record-contracts.md)
- [Building from source](docs/building.md)
- [Development](docs/development.md)
- [Packaging](docs/packaging.md)

## Status

Holder Kit is under active development. The current API covers projects, cards, explicit connections, tags, milestones and analytical exports, with more of the `libholder` API to follow.

## Licence

See [LICENSE](LICENSE).
