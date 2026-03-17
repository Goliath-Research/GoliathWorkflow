"""
Network plot for pathway/module graph: build pathway similarity graph with node attributes,
export as interactive Plotly HTML (and optionally PyVis or Cytoscape.js).
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)


def build_pathway_similarity_graph(
    pathway_to_module_id: Dict[str, int],
    pathway_to_genes: Dict[str, Set[str]],
    similarity_threshold: float,
    module_id_to_label: Dict[int, str],
    use_jaccard: bool = True,
):
    """
    Build a NetworkX graph of pathways with edges where Jaccard similarity >= threshold.
    Attach node attributes: module_label, n_genes, module_id.

    Returns:
        nx.Graph with nodes = pathways, edges = similarity above threshold.
    """
    from .pathway_graph import build_similarity_graph

    if not pathway_to_genes:
        return nx.Graph()

    G, _ = build_similarity_graph(
        pathway_to_genes,
        similarity_threshold=similarity_threshold,
        use_jaccard=use_jaccard,
    )

    for node in G.nodes():
        mid = pathway_to_module_id.get(node, -1)
        genes = pathway_to_genes.get(node, set())
        G.nodes[node]["module_id"] = mid
        G.nodes[node]["module_label"] = module_id_to_label.get(mid, "Other")
        G.nodes[node]["n_genes"] = len(genes)

    return G


def plot_pathway_network_plotly(
    G: nx.Graph,
    output_path: Path,
    layout: str = "spring",
    node_size_by: str = "n_genes",
) -> None:
    """
    Compute layout with NetworkX, build Plotly figure (nodes colored by module, sized by n_genes),
    write interactive HTML to output_path.
    """
    import plotly.graph_objects as go

    if not G.nodes():
        logger.warning("Empty graph; skipping Plotly network plot.")
        return

    if layout == "spring":
        pos = nx.spring_layout(G, seed=42, k=1.5)
    elif layout == "kamada_kawai":
        pos = nx.kamada_kawai_layout(G)
    else:
        pos = nx.spring_layout(G, seed=42, k=1.5)

    # Unique module labels for color mapping
    labels = sorted({G.nodes[n].get("module_label", "Other") for n in G.nodes()})
    label_to_idx = {L: i for i, L in enumerate(labels)}
    colors = [label_to_idx.get(G.nodes[n].get("module_label", "Other"), 0) for n in G.nodes()]

    x = [pos[n][0] for n in G.nodes()]
    y = [pos[n][1] for n in G.nodes()]
    sizes = [G.nodes[n].get(node_size_by, 5) for n in G.nodes()]
    # Scale for visibility (e.g. 8–25)
    min_s, max_s = min(sizes) or 1, max(sizes) or 1
    if max_s > min_s:
        sizes = [8 + 17 * (s - min_s) / (max_s - min_s) for s in sizes]
    else:
        sizes = [12] * len(sizes)

    hover_text = []
    for n in G.nodes():
        lab = G.nodes[n].get("module_label", "Other")
        ng = G.nodes[n].get("n_genes", 0)
        hover_text.append(f"<b>{n}</b><br>Module: {lab}<br>Genes: {ng}")

    node_trace = go.Scatter(
        x=x,
        y=y,
        mode="markers+text",
        marker=dict(
            size=sizes,
            color=colors,
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(title="Module"),
        ),
        text=[G.nodes[n].get("module_label", "Other") for n in G.nodes()],
        textposition="top center",
        textfont=dict(size=9),
        hovertext=hover_text,
        hoverinfo="text",
        name="",
    )

    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.8, color="#888"),
        hoverinfo="none",
        mode="lines",
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        showlegend=False,
        title="Pathway similarity network (nodes = pathways, colored by module)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(b=20, l=20, r=20, t=40),
        hovermode="closest",
        plot_bgcolor="white",
    )
    fig.write_html(str(output_path))
    logger.info(f"Wrote Plotly network plot: {output_path}")


def write_network_plots(
    output_dir: Path,
    pathway_to_module_id: Dict[str, int],
    pathway_to_genes: Dict[str, Set[str]],
    merged_df: pd.DataFrame,
    module_id_to_label: Dict[int, str],
    similarity_threshold: float,
    network_plot: str,
) -> None:
    """
    Generate network plot(s) according to network_plot: 'plotly', 'pyvis', 'cytoscape', or 'all'.
    Skips if network_plot is None or 'none'.
    """
    if not network_plot or network_plot.lower() == "none":
        return

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    G = build_pathway_similarity_graph(
        pathway_to_module_id,
        pathway_to_genes,
        similarity_threshold,
        module_id_to_label,
    )
    if not G.nodes():
        return

    modes = ["plotly", "pyvis", "cytoscape"] if network_plot.lower() == "all" else [network_plot.lower()]

    for mode in modes:
        if mode == "plotly":
            out_path = output_dir / "pathway_network_plotly.html"
            plot_pathway_network_plotly(G, out_path)
        elif mode == "pyvis":
            try:
                _write_pyvis_html(G, output_dir / "pathway_network_pyvis.html")
            except ImportError:
                logger.warning("PyVis not installed; skipping pathway_network_pyvis.html")
        elif mode == "cytoscape":
            _write_cytoscape_html(G, output_dir)


def _write_pyvis_html(G: nx.Graph, output_path: Path) -> None:
    """Export graph to a single HTML file using PyVis (vis.js)."""
    from pyvis.network import Network

    net = Network(
        height="600px",
        width="100%",
        directed=False,
        notebook=False,
    )
    net.from_nx(G)
    net.set_options("""
    var options = {
      "nodes": {
        "font": { "size": 12 },
        "scaling": { "label": { "enabled": true } }
      },
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "stabilization": { "iterations": 150 }
      }
    }
    """)
    net.write_html(str(output_path))
    logger.info(f"Wrote PyVis network plot: {output_path}")


def _write_cytoscape_html(G: nx.Graph, output_dir: Path) -> None:
    """Export graph to Cytoscape.js HTML + JSON."""
    import json

    nodes_cy = []
    for n in G.nodes():
        lab = G.nodes[n].get("module_label", "Other")
        ng = G.nodes[n].get("n_genes", 0)
        nodes_cy.append({"data": {"id": n, "label": n[:40], "module": lab, "n_genes": ng}})

    edges_cy = [{"data": {"source": u, "target": v}} for u, v in G.edges()]

    json_path = output_dir / "pathway_network_cytoscape.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes_cy, "edges": edges_cy}, f, indent=2)

    html = _cytoscape_html_template(nodes_cy, edges_cy)
    html_path = output_dir / "pathway_network_cytoscape.html"
    html_path.write_text(html, encoding="utf-8")
    logger.info(f"Wrote Cytoscape.js network: {html_path}, {json_path}")


def _cytoscape_html_template(nodes_cy: List[Dict], edges_cy: List[Dict]) -> str:
    """Single HTML that loads Cytoscape.js from CDN and renders the graph."""
    import json

    data_js = json.dumps({"nodes": nodes_cy, "edges": edges_cy})
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Pathway network (Cytoscape.js)</title>
  <script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
  <style>
    body {{ font-family: sans-serif; margin: 0; }}
    #cy {{ width: 100%; height: 90vh; }}
  </style>
</head>
<body>
  <h2>Pathway similarity network</h2>
  <div id="cy"></div>
  <script>
    var data = {data_js};
    var cy = cytoscape({{
      container: document.getElementById('cy'),
      elements: data.nodes.concat(data.edges),
      style: [
        {{
          selector: 'node',
          style: {{
            'label': 'data(label)',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            'font-size': 10,
            'width': 20,
            'height': 20,
            'background-color': '#6fb1fc'
          }}
        }},
        {{
          selector: 'edge',
          style: {{ 'width': 0.8, 'line-color': '#ccc' }}
        }}
      ],
      layout: {{ name: 'cose' }}
    }});
  </script>
</body>
</html>
"""
