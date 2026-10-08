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

lab = holderkit.create("Research")
holder = lab.context
project = lab.project

evidence = holder.create_card(
    project.project_id,
    "Read paper",
    "Collect evidence for the report.",
)
report = holder.create_card(
    project.project_id,
    "Write report",
    "Summarise the findings.",
)

print(evidence.title)
```

The following sections use `holder` to work with this project. To analyse an
existing project instead, start with `lab = holderkit.clone(remote_url)` and use
the same context and analysis methods.

## Add a connection, a tag and a milestone

```python
from datetime import datetime, timezone

review_at = int(datetime(2026, 10, 12, 9, tzinfo=timezone.utc).timestamp())

holder.connections.add(
    report.card_id, evidence.card_id, "depends_on", "Needs evidence"
)
holder.tags.add(evidence.card_id, "todo")
holder.milestones.add(evidence.card_id, review_at)
```

The explicit connection points from the report to its evidence. Connections
can have custom kinds and optional labels. Tags use core's semantic tag
operations. Milestones use integer Unix seconds; this one marks a review at
09:00 UTC on 12 October 2026.

These calls write to Holder immediately. See the
[record contracts](record-contracts.md) for tag result enums, milestone updates
and mutation limits.

## Export ordinary Python records

```python
records = holder.cards.to_records(
    project.project_id, include_content=True
)

for card in records:
    print(card["title"], card["content"])
```

Records contain standard-library values and remain usable after the context
closes. Card exports omit bodies by default; `include_content=True` adds the
`content` field. Changing an exported dictionary does not update Holder.

## Analyse the project with pandas

```python
tables = holder.to_dataframes(project.project_id, include_content=True)

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
graph = holder.to_networkx(project.project_id)

print("Cards:", graph.number_of_nodes())
print("Connections:", graph.number_of_edges())
for source, target, kind in graph.edges(keys=True):
    print(graph.nodes[source]["title"], kind, graph.nodes[target]["title"])
```

The result is a detached NetworkX `MultiDiGraph`. Card IDs identify nodes and
connection kinds identify edges, allowing multiple kinds between the same
two cards. For this example, the graph has two cards and one connection.
Editing the graph does not modify Holder.

When you have finished, close the project:

```python
lab.close()
```

Your edits are saved locally, and exported records, tables and graphs remain
usable after closing. See [Advanced: storage and reopening](workspaces.md) for
returning to saved work or choosing a storage directory.

For more examples, see [`examples/`](../examples/). The
[detached record contracts](record-contracts.md) describe schemas, filtering
and cross-project graph targets in detail.
