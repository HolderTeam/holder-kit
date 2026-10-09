# Holder Kit

**Analyse, transform and import Holder data with Python.**

Holder Kit gives Python programs direct access to Holder projects, cards, connections, tags and milestones.

Typical uses include:

- **Data analysis** — load Holder data into pandas and explore it with familiar Python tools.
- **Bulk import and transformation** — create or modify large collections of cards programmatically.
- **Machine learning** — extract Holder content for classification, clustering, embeddings, ranking and other experiments.
- **Graph analysis** — export explicit connections between cards to NetworkX.
- **Dataset and corpus preparation** — turn a Holder knowledge base into structured Python records for further processing.
- **Offline automation** — perform maintenance, migration and batch operations without running the Holder daemon.

The base package exposes ordinary Python records and has no data-science dependencies. pandas and NetworkX integrations are available as optional extras.

A typical workflow looks like this:

![AI generated image](docs/workflow.png)

1. You make a new project, or clone an existing one.
2. You do work and analysis.
3. You push your experiment, or discard it.

## A first example

```python
import holderkit

with holderkit.create("Research") as project:
    card = project.create_card(
        "Interesting question",
        "Something worth investigating.",
    )

    print(project.cards.to_records(include_content=True))
```

Or clone an existing Holder project and explore its cards:

```python
with holderkit.clone("git@example.org:research.git") as project:
    for card in project.cards.to_records(include_content=True):
        print(card["title"], card["content"])
```

Replace the example URL with your project's Git remote. Holder Kit chooses
local storage automatically. These examples need Git installed.

When your experiment is ready, publish it while the project is open with
`project.push(remote_url="git@example.org:research.git", branch="experiments/results")`.
Use `project.close()` to keep your work, or `project.discard(confirm=True)` to
remove it locally. See [Publishing and finishing a project](docs/publication.md).

Follow the [walkthrough](docs/walkthrough.md) to create connected cards, add tags
and milestones, and analyse detached records with pandas and NetworkX.

For larger projects, process cards a batch at a time:

```python
for batch in project.cards(batch_size=256, include_content=True):
    for card in batch:
        print(card["title"], card["content"])
```

Use this while the project is open. Each batch contains ordinary Python records.

## Installation

Holder Kit is currently in early development.

The Python distribution is named `holder-kit` and the import package is `holderkit`.

See [Building Holder Kit](docs/building.md) for installing the current version from source.

Ubuntu packages are also available as `python3-holder-kit` for supported Holder package repositories.

## How Holder Kit fits into Holder

Holder Kit is a Python binding over `libholder`, running Holder directly inside
the Python process. This makes it suitable for scripts, notebooks, data analysis
and applications that want to embed Holder functionality.

To control a running Holder installation through the Framework API, use
[holder-python](https://github.com/HolderTeam/holder-framework/tree/main/python).

Holder Kit is versioned independently from the
[Holder Framework](https://github.com/HolderTeam/holder-framework) and
[core library](https://github.com/HolderTeam/holder-core).

## Examples

The repository includes examples covering:

- card creation and lifecycle;
- detached Python records;
- pandas analysis;
- connection graphs;
- tag analysis;
- milestone and calendar analysis;
- creating projects, retaining local edits and explicitly finishing an experiment.

See the [`examples/`](examples/) directory.

## Documentation

- [Walkthrough](docs/walkthrough.md)
- [Publishing and finishing a project](docs/publication.md)
- [Detached record contracts](docs/record-contracts.md)
- [Advanced: storage and reopening](docs/storage.md)
- [Building from source](docs/building.md)
- [Development](docs/development.md)
- [Packaging](docs/packaging.md)

## Status

Holder Kit is under active development. The current API covers projects, cards, explicit connections, tags, milestones and analytical exports, with more of the `libholder` API to follow.

## Licence

See [LICENSE](LICENSE).
