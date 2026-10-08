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

The planned private-workspace workflow looks like this:

![AI generated image](docs/workflow.png)

1. You make a new project, or clone an existing one.
2. You do work and analysis.
3. You push your experiment, or discard it.

Managed create/clone/reopen and publish/discard entry points are planned. The
current API provides embedded contexts and entity operations; the example below
uses that existing low-level API.

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

Follow the [walkthrough](docs/walkthrough.md) to create connected cards, add tags
and milestones, and analyse detached records with pandas and NetworkX.

## Installation

Holder Kit is currently in early development. Published wheels are available:

```sh
python -m pip install holder-kit
```

Wheels support CPython 3.10–3.14 on Linux x86_64 (glibc 2.39+), Windows x86_64
and macOS ARM64 (macOS 15+). See [Packaging](docs/packaging.md) for platform
requirements and source-build alternatives.

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
- milestone and calendar analysis.

See the [`examples/`](examples/) directory.

## Documentation

- [Walkthrough](docs/walkthrough.md)
- [Detached record contracts](docs/record-contracts.md)
- [Building from source](docs/building.md)
- [Development](docs/development.md)
- [Packaging](docs/packaging.md)

## Status

Holder Kit is under active development. The current API covers projects, cards, explicit connections, tags, milestones and analytical exports, with more of the `libholder` API to follow.

## Licence

See [LICENSE](LICENSE).
