from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

import networkx as nx

from .network import build_graph
from .schemas import Action, Asset, SimulationResult, WeatherEvent


class HydraulicModel(Protocol):
    def run(self, actions: list[Action] | None = None) -> SimulationResult: ...


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


class SwmmUnavailableError(RuntimeError):
    """Raised when the optional EPA SWMM runtime cannot be loaded."""


class UnsupportedSwmmActionError(ValueError):
    """Raised instead of silently pretending an unsupported action had an effect."""


class SwmmHydraulicModel:
    """Runs a small EPA SWMM 5.2 model with explicit physical scenario changes.

    The bundled network geometry and rainfall are synthetic and are not field calibrated.
    Results are valid SWMM outputs for this small model, not a Trabzon flood forecast.
    """

    _XSECTION_UPDATES = {
        "A1": ("L_I1", (0.40, 0.0)),
        "A2": ("L_I2", (0.40, 0.0)),
        "A3": ("L_C1", (0.52, 0.0)),
        "A4": ("L_CH1", (0.85, 1.20)),
    }
    _STORAGE_DEPTH_UPDATES = {"A7": ("S1", 0.05)}
    _UNSUPPORTED_ACTIONS = {"A5", "A6"}

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path).resolve()
        if not self.model_path.is_file():
            raise FileNotFoundError(self.model_path)
        self._base_text = self.model_path.read_text(encoding="utf-8")
        self._model_digest = hashlib.sha256(self._base_text.encode("utf-8")).hexdigest()
        self._cache: dict[str, SimulationResult] = {}

    @staticmethod
    def is_available() -> bool:
        try:
            import pyswmm  # noqa: F401
        except (ImportError, OSError):
            return False
        return True

    @classmethod
    def _validate_actions(cls, actions: list[Action]) -> None:
        unsupported = sorted(
            action.id
            for action in actions
            if action.id in cls._UNSUPPORTED_ACTIONS
            or (
                action.id not in cls._XSECTION_UPDATES
                and action.id not in cls._STORAGE_DEPTH_UPDATES
            )
        )
        if unsupported:
            joined = ", ".join(unsupported)
            raise UnsupportedSwmmActionError(
                f"SWMM modelinde fiziksel karşılığı tanımlı olmayan eylemler: {joined}"
            )

    @staticmethod
    def _replace_section_row(
        text: str,
        section: str,
        row_id: str,
        token_updates: dict[int, str],
    ) -> str:
        pattern = re.compile(
            rf"(?ms)(^\[{re.escape(section)}\]\s*$)(.*?)(?=^\[|\Z)"
        )
        match = pattern.search(text)
        if not match:
            raise ValueError(f"SWMM bölümü bulunamadı: {section}")
        block = match.group(2)
        lines = block.splitlines()
        replaced = False
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            tokens = stripped.split()
            if tokens[0] != row_id:
                continue
            for token_index, value in token_updates.items():
                tokens[token_index] = value
            lines[index] = "  ".join(tokens)
            replaced = True
            break
        if not replaced:
            raise ValueError(f"SWMM satırı bulunamadı: [{section}] {row_id}")
        new_block = "\n".join(lines)
        if block.endswith("\n"):
            new_block += "\n"
        return text[: match.start(2)] + new_block + text[match.end(2) :]

    def _scenario_text(
        self, actions: list[Action], green_lid_scenario: bool = False
    ) -> str:
        text = self._base_text
        if green_lid_scenario:
            # Yeşil Altyapı / Doğa Tabanlı Çözümler (NbS / LID):
            # Üst alt havzalarda (SC_I1, SC_I2, SC_I3) %25 geçirimli zemin ve yağmur bahçesi dönüşümü.
            # Geçirimsiz alan yüzdesi (%Imperv) düşürülerek yüzey akışının kaynağında sızdırılması modellenir.
            text = self._replace_section_row(
                text, "SUBCATCHMENTS", "SC_I1", {4: "60"}
            )
            text = self._replace_section_row(
                text, "SUBCATCHMENTS", "SC_I2", {4: "65"}
            )
            text = self._replace_section_row(
                text, "SUBCATCHMENTS", "SC_I3", {4: "55"}
            )
        for action in sorted(actions, key=lambda item: item.id):
            if action.id in self._XSECTION_UPDATES:
                link_id, (geom1, geom2) = self._XSECTION_UPDATES[action.id]
                text = self._replace_section_row(
                    text,
                    "XSECTIONS",
                    link_id,
                    {2: f"{geom1:.3f}", 3: f"{geom2:.3f}"},
                )
            elif action.id in self._STORAGE_DEPTH_UPDATES:
                storage_id, initial_depth = self._STORAGE_DEPTH_UPDATES[action.id]
                text = self._replace_section_row(
                    text,
                    "STORAGE",
                    storage_id,
                    {3: f"{initial_depth:.3f}"},
                )
        return text

    def run(
        self,
        actions: list[Action] | None = None,
        green_lid_scenario: bool = False,
    ) -> SimulationResult:
        actions = actions or []
        self._validate_actions(actions)
        action_ids = sorted(action.id for action in actions)
        payload = {
            "model_sha256": self._model_digest,
            "actions": action_ids,
            "green_lid": green_lid_scenario,
        }
        scenario_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        if scenario_hash in self._cache:
            return self._cache[scenario_hash].model_copy(deep=True)

        try:
            from pyswmm import Nodes, Simulation, SystemStats
        except (ImportError, OSError) as exc:
            raise SwmmUnavailableError(
                "PySWMM/SWMM motoru kullanılamıyor; hydraulic ekstra bağımlılığını kurun."
            ) from exc

        with TemporaryDirectory(prefix="siper-swmm-") as temp_dir:
            temp_path = Path(temp_dir)
            scenario_path = temp_path / "scenario.inp"
            scenario_path.write_text(
                self._scenario_text(actions, green_lid_scenario=green_lid_scenario),
                encoding="utf-8",
            )
            report_path = temp_path / "scenario.rpt"
            output_path = temp_path / "scenario.out"
            with Simulation(
                str(scenario_path),
                reportfile=str(report_path),
                outputfile=str(output_path),
            ) as simulation:
                nodes = Nodes(simulation)
                node_ids = [node.nodeid for node in nodes]
                system_stats = SystemStats(simulation)
                for _ in simulation:
                    pass

                node_stats = {node_id: nodes[node_id].statistics for node_id in node_ids}
                routing_stats = system_stats.routing_stats
                overflow_volume = max(0.0, float(routing_stats["flooding"]))
                continuity_error = float(routing_stats["routing_error"])
                engine_version = str(simulation.engine_version)
                flow_units = str(simulation.flow_units)

        node_flooding = {
            node_id: round(max(0.0, float(stats["flooding_volume"])), 6)
            for node_id, stats in node_stats.items()
        }
        peak_inflow = {
            node_id: round(max(0.0, float(stats["peak_total_inflow"])), 6)
            for node_id, stats in node_stats.items()
        }
        max_depth = {
            node_id: round(max(0.0, float(stats["max_depth"])), 6)
            for node_id, stats in node_stats.items()
        }
        result = SimulationResult(
            scenario_hash=scenario_hash,
            action_ids=action_ids,
            total_impact_index=round(overflow_volume, 6),
            node_impact=node_flooding,
            node_inflow=peak_inflow,
            source="hydraulic_simulation",
            model_label="EPA SWMM 5.2 / SYNTHETIC GEOMETRY / NOT FIELD CALIBRATED",
            overflow_volume_m3=round(overflow_volume, 6),
            max_node_depth_m=max_depth,
            continuity_error_pct=round(continuity_error, 6),
            engine_version=engine_version,
            flow_units=flow_units,
        )
        self._cache[scenario_hash] = result
        return result.model_copy(deep=True)
