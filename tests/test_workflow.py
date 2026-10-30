import pytest

from siper.optimizer import optimize_plan
from siper.schemas import WorkOrderStatus
from siper.workflow import (
    create_work_orders,
    mark_completed,
    replan_after_verification,
    verify_order,
)


def test_completed_requires_verification(model, actions, teams):
    order = create_work_orders(optimize_plan(model, actions, teams))[0]
    completed = mark_completed(order)
    assert completed.status == WorkOrderStatus.COMPLETED_PENDING_VERIFICATION
    with pytest.raises(ValueError):
        verify_order(completed, None)


def test_replanning_updates_remaining_jobs(model, assets, event, actions, teams):
    initial = optimize_plan(model, actions, teams)
    orders = create_work_orders(initial)
    verified = verify_order(mark_completed(orders[0]), {"class": "unblocked", "source": "operator_input"})
    replanned = replan_after_verification(assets, event, actions, teams, [verified])
    assert verified.action_id not in replanned.selected_action_ids
    assert replanned.plan_id != initial.plan_id


def test_full_demo(model, assets, event, actions, teams):
    baseline = model.run()
    plan = optimize_plan(model, actions, teams)
    assert plan.planned_impact_index < baseline.total_impact_index
    order = create_work_orders(plan)[0]
    verified = verify_order(mark_completed(order), {"class": "unblocked", "source": "operator_input"})
    new_plan = replan_after_verification(assets, event, actions, teams, [verified])
    assert new_plan.assignments
