from __future__ import annotations

import networkx as nx

from .schemas import Asset, AssetType


def build_graph(assets: list[Asset]) -> nx.DiGraph:
    graph = nx.DiGraph()
    asset_map = {asset.id: asset for asset in assets}
    if len(asset_map) != len(assets):
        raise ValueError("Varlık kimlikleri benzersiz olmalıdır")
    for asset in assets:
        graph.add_node(asset.id, asset=asset)
    for asset in assets:
        for downstream_id in asset.downstream_ids:
            if downstream_id not in asset_map:
                raise ValueError(f"Bilinmeyen aşağı akım varlığı: {downstream_id}")
            graph.add_edge(asset.id, downstream_id)
        for upstream_id in asset.upstream_ids:
            if upstream_id not in asset_map:
                raise ValueError(f"Bilinmeyen yukarı akım varlığı: {upstream_id}")
            if asset.id not in asset_map[upstream_id].downstream_ids:
                raise ValueError(f"Tutarsız bağlantı: {upstream_id} -> {asset.id}")
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Demo proxy ağı çevrimsiz olmalıdır")
    return graph


def network_diagnostics(assets: list[Asset]) -> dict[str, object]:
    graph = build_graph(assets)
    outfalls = [asset.id for asset in assets if asset.type == AssetType.OUTFALL]
    unreachable = [
        node
        for node in graph.nodes
        if node not in outfalls and not any(nx.has_path(graph, node, outfall) for outfall in outfalls)
    ]
    return {
        "weakly_connected": nx.is_weakly_connected(graph),
        "outfalls": outfalls,
        "unreachable_to_outfall": unreachable,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
    }


def travel_minutes(graph: nx.DiGraph, origin: str, destination: str) -> int:
    if origin == destination:
        return 2
    try:
        hops = nx.shortest_path_length(graph.to_undirected(), origin, destination)
    except nx.NetworkXNoPath:
        return 10_000
    return 5 + 4 * hops
