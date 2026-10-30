from __future__ import annotations

import hashlib
import json

import networkx as nx

from .network import build_graph
from .schemas import Action, Asset, SimulationResult, WeatherEvent


class ProxyHydraulicModel:
    """Karar algoritması demosu; fiziksel veya kalibre edilmiş hidrolik model değildir."""

    def __init__(self, assets: list[Asset], event: WeatherEvent):
        self.assets = assets
        self.event = event
        self.graph = build_graph(assets)
        self.asset_map = {asset.id: asset for asset in assets}
        self._cache: dict[str, SimulationResult] = {}

    def run(self, actions: list[Action] | None = None) -> SimulationResult:
        actions = actions or []
        capacity_overrides = {action.asset_id: action.capacity_factor_after for action in actions}
        action_ids = sorted(action.id for action in actions)
        payload = {
            "scenario": self.event.scenario_id,
            "actions": action_ids,
            "capacities": capacity_overrides,
        }
        scenario_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        if scenario_hash in self._cache:
            return self._cache[scenario_hash].model_copy(deep=True)
        rain_load = 22.0 * self.event.rain_intensity_index
        node_outflow: dict[str, float] = {}
        node_inflow: dict[str, float] = {}
        node_impact: dict[str, float] = {}

        for node_id in nx.topological_sort(self.graph):
            asset = self.asset_map[node_id]
            upstream_flow = sum(node_outflow[parent] for parent in self.graph.predecessors(node_id))
            local_flow = rain_load * asset.local_runoff_weight
            inflow = upstream_flow + local_flow
            factor = capacity_overrides.get(
                node_id,
                asset.hydraulic_capacity_factor if asset.hydraulic_capacity_factor is not None else 1.0,
            )
            capacity = asset.base_capacity * factor
            overflow = max(0.0, inflow - capacity)
            # Darboğazın aşağı akıma ve kritik alanlara etkisi doğrusal olmayan bir vekil indekstir.
            saturation_penalty = max(0.0, inflow / max(capacity, 0.01) - 0.85) ** 2
            node_impact[node_id] = round(
                (overflow + saturation_penalty * 2.5) * asset.criticality_weight,
                4,
            )
            node_inflow[node_id] = round(inflow, 4)
            node_outflow[node_id] = min(inflow, capacity)

        result = SimulationResult(
            scenario_hash=scenario_hash,
            action_ids=action_ids,
            total_impact_index=round(sum(node_impact.values()), 4),
            node_impact=node_impact,
            node_inflow=node_inflow,
        )
        self._cache[scenario_hash] = result
        return result.model_copy(deep=True)
