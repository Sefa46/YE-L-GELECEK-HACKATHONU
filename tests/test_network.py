import networkx as nx

from siper.network import build_graph, network_diagnostics


def test_network_is_connected(assets):
    graph = build_graph(assets)
    diagnostics = network_diagnostics(assets)
    assert nx.is_weakly_connected(graph)
    assert diagnostics["unreachable_to_outfall"] == []
    assert diagnostics["node_count"] >= 10


def test_visual_obstruction_not_equal_hydraulic_capacity(assets):
    observed = [asset for asset in assets if asset.blockage_visual_fraction is not None]
    assert observed
    assert any(
        asset.blockage_visual_fraction != asset.hydraulic_capacity_factor
        for asset in observed
    )
