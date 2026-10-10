# Holder Kit walkthrough

This walkthrough builds a small research project, then exports its data for
Python analysis. Run the Python blocks in order in one session or notebook.
Holder Kit chooses local storage automatically.

## Install Holder Kit

Follow [Building Holder Kit](building.md) to install from source. The developer
setup includes both pandas and NetworkX, which are needed for the last two
sections. The base package is enough for creating data and exporting records.

## Create a project and cards

```python
import holderkit

project = holderkit.create("Research")

evidence = project.create_card(
    "Read paper",
    "Collect evidence for the report.",
)
report = project.create_card(
    "Write report",
    "Summarise the findings.",
)

print(evidence.title)
```

The following sections use `project` to work with this project. To analyse an
existing project instead, start with `project = holderkit.clone(remote_url)` and use
the same analysis methods.

## Arrange cards

```python
evidence.move(into=report)
parent = evidence.parent
if parent is not None:
    print(parent.title)

evidence.move(before=report)
assert evidence.parent is None

evidence.move(after=report)
```

`into` makes a card a child of the target. `before` and `after` place it beside
the target, sharing its parent. Supply exactly one target Card from the same
project. These calls save immediately and return the moved Card. The live
`parent` property returns a Card owned by the same Project, or `None` at the
root. Core rejects moves that would create a cycle.

## Add a connection, a tag and a milestone

```python
from datetime import datetime, timezone

review_at = int(datetime(2026, 10, 12, 9, tzinfo=timezone.utc).timestamp())

report.connections.add(evidence, kind="depends_on", label="Needs evidence")
evidence.tags.add("todo")
evidence.milestones.add(review_at)
```

The explicit connection points from the report to its evidence. Connections
can have custom kinds and optional labels. Tags use core's semantic tag
operations. Milestones use integer Unix seconds; this one marks a review at
09:00 UTC on 12 October 2026.

Use `evidence.tags.list()`, `report.connections.to_records()` or
`evidence.milestones.list()` to read that card's current values. Each collection
also provides detached records and optional pandas DataFrames. To update a
milestone, pass its ID and the fields you want to change:

```python
milestone = evidence.milestones.list()[0]
evidence.milestones.update(milestone["milestone_id"], {"description": "Review evidence"})
```

Project collections remain available for project-wide queries and exports.
Connection targets are Cards in the same Context, including other projects;
use a live target when adding. Removing a connection can also target a Card
in Trash. All collection operations require the source Card to be live and its
Project open.

These calls write to Holder immediately. See the
[record contracts](record-contracts.md) for tag result enums, milestone updates
and mutation limits.

## Export ordinary Python records

```python
records = project.cards.to_records(
    include_content=True
)

for card in records:
    print(card["title"], card["content"])
```

Records contain standard-library values and remain usable after the project
closes. Card exports omit bodies by default; `include_content=True` adds the
`content` field. Changing an exported dictionary does not update Holder.

For a larger project, read batches instead of collecting every card at once:

```python
for batch in project.cards(batch_size=256, include_content=True):
    for card in batch:
        print(card["title"], card["content"])
```

Calling `project.cards(...)` returns a lazy iterator of record lists. The final
batch may be smaller. Keep the project open while iterating; each batch contains
ordinary Python records. Omit `include_content` for metadata-only records.

Select a useful subset with a tag, root cards, or the immediate children of a card:

```python
for batch in project.cards(tag="todo", include_content=True):
    for card in batch:
        print(card["title"], card["content"])

for batch in project.cards(roots=True):
    print([card["title"] for card in batch])

for batch in project.cards(parent_card_id=report.card_id, tag="todo"):
    print([card["title"] for card in batch])
```

Tags match without regard to case; pass the name without `#`. Tag and hierarchy
filters can be combined. `roots=True` and `parent_card_id` are alternatives.
Use `order="card_id"` for ascending card IDs or `order="updated"` for the most
recently updated first. Filtered batches require a Core SDK with collection
pagination support; older SDKs raise `NotImplementedError`.

## Analyse the project with pandas

```python
tables = project.to_dataframes(include_content=True)

cards = tables["cards"]
projects = tables["projects"]

analysis = cards.assign(content_length=cards["content"].str.len()).merge(
    projects[["project_id", "name"]],
    on="project_id",
)
print(analysis[["name", "title", "content_length"]].to_string(index=False))

tagged_cards = tables["tags"].merge(
    cards[["project_id", "card_id", "title"]],
    on=["project_id", "card_id"],
)
print(tagged_cards[["title", "tag"]].to_string(index=False))
```

`to_dataframes()` returns five tables: `projects`, `cards`, `connections`, `tags`
and `milestones`. Here they are scoped to the research project.
Editing the DataFrames does not write back.
Exporting the tables makes separate core reads rather than an atomic snapshot.

## Explore the connection graph

```python
graph = project.to_networkx()

print("Cards:", graph.number_of_nodes())
print("Connections:", graph.number_of_edges())
for source, target, kind in graph.edges(keys=True):
    print(graph.nodes[source]["title"], kind, graph.nodes[target]["title"])
```

The result is a detached NetworkX `MultiDiGraph`. Card IDs identify nodes and
connection kinds identify edges, allowing multiple kinds between the same
two cards. For this example, the graph has two cards and one connection.
Editing the graph does not modify Holder.

## Edit, trash and restore a card

Cards belong to their Project and read current state:

```python
assert evidence.project is project
saved = evidence.to_record()
evidence.update("New evidence for the report.")
print(evidence.content)
```

`saved` remains a detached copy of the earlier values. Live Cards need an open
Project; export records before closing if you want to retain their values.

```python
evidence.trash()  # evidence.delete() does the same
print([card.title for card in project.cards.trashed()])
evidence = evidence.restore()
```

Trashing a parent keeps its children live and promotes them into its place.
Restoring brings back that card alone. After reopening a project, find cards in
`project.cards.trashed()` and call `restore()` on the one you want. While a card
is in Trash, read metadata with `card.to_record(include_content=False)`; restore
it before reading its body.

For permanent removal, first trash the card, then use `card.purge()` or
`card.delete(hard=True)`. Both require the card to already be in Trash. The same
operations are available as `project.trash(card)`, `project.restore(card)` and
`project.purge(card)`.

To publish your experiment, push it to a new branch in a repository you can write
to: `project.push(remote_url=remote_url, branch="experiments/results")`.
You can continue editing and push to that branch again. See
[Publishing and finishing a project](publication.md) for reviewing a push and
deliberately discarding local work with `project.discard(confirm=True)`.

To keep your work locally, close the project:

```python
project.close()
```

Your edits are saved locally, and exported records, tables and graphs remain
usable after closing. See [Advanced: storage and reopening](storage.md) for
returning to saved work or choosing a storage directory.

For more examples, see [`examples/`](../examples/). The
[detached record contracts](record-contracts.md) describe schemas, filtering
and cross-project graph targets in detail.
