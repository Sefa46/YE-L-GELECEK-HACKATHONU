from __future__ import annotations

from datetime import datetime
try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SourceType(StrEnum):
    REAL_OBSERVATION = "real_observation"
    FORECAST = "forecast"
    OPEN_DATASET = "open_dataset"
    SYNTHETIC_SCENARIO = "synthetic_scenario"
    HYDRAULIC_SIMULATION = "hydraulic_simulation"
    HEURISTIC_ESTIMATE = "heuristic_estimate"
    OPERATOR_INPUT = "operator_input"
    SIMULATED_SENSOR = "simulated_sensor"


class AssetType(StrEnum):
    INLET = "inlet"
    GRATE = "grate"
    CULVERT = "culvert"
    PIPE = "pipe"
    COLLECTOR = "collector"
    OPEN_CHANNEL = "open_channel"
    PUMP_STATION = "pump_station"
    STORAGE = "storage"
    OUTFALL = "outfall"


class ObservationClass(StrEnum):
    UNBLOCKED = "unblocked"
    PARTIAL = "partial"
    SEVERE = "severe"
    UNKNOWN = "unknown"


class WorkOrderStatus(StrEnum):
    CANDIDATE = "candidate"
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    IN_PROGRESS = "in_progress"
    COMPLETED_PENDING_VERIFICATION = "completed_pending_verification"
    VERIFIED = "verified"
    FAILED = "failed"
    INACCESSIBLE = "inaccessible"
    CANCELLED = "cancelled"


class Asset(BaseModel):
    id: str
    name: str
    type: AssetType
    lat: float | None = None
    lon: float | None = None
    upstream_ids: list[str] = Field(default_factory=list)
    downstream_ids: list[str] = Field(default_factory=list)
    drainage_zone_id: str
    image_path: str | None = None
    blockage_visual_fraction: float | None = Field(default=None, ge=0, le=1)
    hydraulic_capacity_factor: float | None = Field(default=None, ge=0, le=1)
    base_capacity: float = Field(gt=0)
    local_runoff_weight: float = Field(default=1.0, ge=0)
    water_level_m: float | None = Field(default=None, ge=0)
    observation_time: datetime | None = None
    observation_source: SourceType
    confidence: float | None = Field(default=None, ge=0, le=1)
    inspection_accessible: bool = True
    criticality_tags: list[str] = Field(default_factory=list)
    criticality_weight: float = Field(default=1.0, ge=1)
    condition_notes: str = ""


class WeatherEvent(BaseModel):
    event_id: str
    name: str
    starts_at: datetime
    horizon_minutes: int = Field(gt=0)
    hourly_rain_mm: list[float]
    scenario_id: str
    source: SourceType
    reliability_note: str

    @property
    def rain_intensity_index(self) -> float:
        if not self.hourly_rain_mm:
            return 0.0
        return min(2.0, sum(self.hourly_rain_mm) / (len(self.hourly_rain_mm) * 20.0))


class Action(BaseModel):
    id: str
    asset_id: str
    action_type: str
    name: str
    duration_minutes: int = Field(gt=0)
    required_equipment: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    earliest_start_minute: int = Field(default=0, ge=0)
    capacity_factor_after: float = Field(ge=0, le=1)
    source: SourceType = SourceType.SYNTHETIC_SCENARIO
    safety_note: str = "Simule müdahale; fiziksel saha komutu değildir."


class Team(BaseModel):
    id: str
    name: str
    skills: list[str]
    equipment: list[str]
    start_asset_id: str


class SimulationResult(BaseModel):
    scenario_hash: str
    action_ids: list[str]
    total_impact_index: float = Field(ge=0)
    node_impact: dict[str, float]
    node_inflow: dict[str, float]
    source: SourceType = SourceType.HEURISTIC_ESTIMATE
    model_label: str = "HEURISTIC / NOT HYDRAULICALLY VALIDATED"
    overflow_volume_m3: None = None


class Assignment(BaseModel):
    team_id: str
    action_id: str
    start_minute: int
    end_minute: int
    travel_minutes: int


class Plan(BaseModel):
    plan_id: str
    selected_action_ids: list[str]
    assignments: list[Assignment]
    rejected: dict[str, str]
    baseline_impact_index: float
    planned_impact_index: float
    simulated_benefit: float
    deadline_minutes: int
    source: SourceType = SourceType.HEURISTIC_ESTIMATE

    @model_validator(mode="after")
    def validate_assignments(self) -> "Plan":
        ids = [item.action_id for item in self.assignments]
        if len(ids) != len(set(ids)):
            raise ValueError("Bir görev aynı planda birden fazla atanamaz")
        if any(item.end_minute > self.deadline_minutes for item in self.assignments):
            raise ValueError("Plan son zamanı aşıyor")
        return self


class WorkOrder(BaseModel):
    id: str
    action_id: str
    team_id: str
    status: WorkOrderStatus
    verification_observation: dict[str, Any] | None = None
    event_log: list[dict[str, Any]] = Field(default_factory=list)
