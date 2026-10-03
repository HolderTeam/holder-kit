"""Compare detached connection-table joins with a graph over temporary data."""

from pathlib import Path
from tempfile import TemporaryDirectory

import networkx as nx

import holder


with TemporaryDirectory(prefix="holder-graph-example-") as temporary:
    with holder.open(Path(temporary) / "data") as context:
        project = context.create_project("Demo")
        first = context.create_card(project.project_id, "Collect evidence")
        second = context.create_card(project.project_id, "Write report")
        context.create_card(project.project_id, "Independent note")
        context.connections.add(second.card_id, first.card_id, "depends_on", "Evidence needed")
        context.connections.add(second.card_id, first.card_id, "references")
        cards = context.cards.to_dataframe(project.project_id)
        connections = context.connections.to_dataframe(project.project_id)
        graph = context.to_networkx(project.project_id)

    joined = connections.merge(
        cards[["card_id", "title"]], left_on="from_card_id", right_on="card_id",
    )
    print(joined[["title", "kind", "to_title"]].to_string(index=False))
    print("Nodes:", graph.number_of_nodes(), "connections:", graph.number_of_edges())
    print("Degree centrality:", nx.degree_centrality(graph))
