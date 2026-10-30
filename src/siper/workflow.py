from __future__ import annotations

from datetime import datetime, timezone

from .optimizer import optimize_plan
from .schemas import Action, Asset, Plan, SourceType, Team, WorkOrder, WorkOrderStatus
from .hydraulics import ProxyHydraulicModel
from .schemas import WeatherEvent


def _event(status: WorkOrderStatus, reason: str) -> dict[str, str]:
    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "status": status.value,
        "reason": reason,
        "source": SourceType.OPERATOR_INPUT.value,
    }


def create_work_orders(plan: Plan) -> list[WorkOrder]:
    return [
        WorkOrder(
            id=f"WO-{assignment.action_id}",
            action_id=assignment.action_id,
            team_id=assignment.team_id,
            status=WorkOrderStatus.ASSIGNED,
            event_log=[_event(WorkOrderStatus.ASSIGNED, "Simülasyon planından oluşturuldu")],
        )
        for assignment in plan.assignments
    ]


def mark_completed(order: WorkOrder) -> WorkOrder:
    updated = order.model_copy(deep=True)
    updated.status = WorkOrderStatus.COMPLETED_PENDING_VERIFICATION
    updated.event_log.append(
        _event(updated.status, "Ekip tamamlandı bildirdi; yeni gözlem bekleniyor")
    )
    return updated


def verify_order(order: WorkOrder, observation: dict[str, object] | None) -> WorkOrder:
    if not observation:
        raise ValueError("Doğrulama için yeni gözlem zorunludur")
    if order.status != WorkOrderStatus.COMPLETED_PENDING_VERIFICATION:
        raise ValueError("Yalnız tamamlanma bildirimi yapılmış iş doğrulanabilir")
    updated = order.model_copy(deep=True)
    updated.status = WorkOrderStatus.VERIFIED
    updated.verification_observation = observation
    updated.event_log.append(_event(updated.status, "Yeni operatör gözlemiyle doğrulandı"))
    return updated


def replan_after_verification(
    assets: list[Asset],
    event: WeatherEvent,
    actions: list[Action],
    teams: list[Team],
    orders: list[WorkOrder],
    deadline_minutes: int = 120,
) -> Plan:
    action_map = {action.id: action for action in actions}
    verified_ids = {order.action_id for order in orders if order.status == WorkOrderStatus.VERIFIED}
    updated_assets = [asset.model_copy(deep=True) for asset in assets]
    for asset in updated_assets:
        for action_id in verified_ids:
            action = action_map[action_id]
            if action.asset_id == asset.id:
                asset.hydraulic_capacity_factor = action.capacity_factor_after
    remaining = [action for action in actions if action.id not in verified_ids]
    return optimize_plan(
        ProxyHydraulicModel(updated_assets, event),
        remaining,
        teams,
        deadline_minutes=deadline_minutes,
    )
