from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

CURRENT_FEATURE_SCHEMA_VERSION = "v1.1"

MODEL_FEATURES = [
    "loss_mean_30s",
    "tx_dropped_max",
    "control_plane_rtt_ms",
    "rx_bytes_slope",
    "tx_bytes_rate",
]


class CalibrationInfo(BaseModel):
    method: Optional[str] = None
    status: str = "not_calibrated"


class ModelMetadata(BaseModel):
    run_id: Optional[str] = None
    model_version: str = "1.1.0"
    feature_schema_version: str = CURRENT_FEATURE_SCHEMA_VERSION
    feature_names: List[str] = Field(default_factory=lambda: MODEL_FEATURES)
    training_data_hash: Optional[str] = None
    training_commit: Optional[str] = None
    git_dirty: bool = False
    decision_threshold: float = 0.5
    calibration: CalibrationInfo = Field(default_factory=CalibrationInfo)
    creation_time: str
    data_origin: str = "synthetic"
