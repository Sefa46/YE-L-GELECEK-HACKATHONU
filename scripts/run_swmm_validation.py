from __future__ import annotations

import json
from pathlib import Path

from siper.hydraulics import SwmmHydraulicModel
from siper.storage import load_actions, project_root


def summarize(result) -> dict[str, object]:
    return {
        "scenario_hash": result.scenario_hash,
        "action_ids": result.action_ids,
        "overflow_volume_m3": result.overflow_volume_m3,
        "node_flooding_volume_m3": result.node_impact,
        "max_node_depth_m": result.max_node_depth_m,
        "continuity_error_pct": result.continuity_error_pct,
        "engine_version": result.engine_version,
        "flow_units": result.flow_units,
        "source": result.source.value,
        "model_label": result.model_label,
    }


def main() -> None:
    root = project_root()
    model = SwmmHydraulicModel(root / "data" / "swmm" / "siper_small_network.inp")
    action_map = {action.id: action for action in load_actions()}
    scenarios = {
        "baseline": model.run(),
        "culvert_restored": model.run([action_map["A3"]]),
        "three_upstream_restorations": model.run(
            [action_map["A1"], action_map["A2"], action_map["A3"]]
        ),
    }
    payload = {name: summarize(result) for name, result in scenarios.items()}
    output_path = root / "data" / "swmm" / "validation_results.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nKaydedildi: {output_path}")


if __name__ == "__main__":
    main()
