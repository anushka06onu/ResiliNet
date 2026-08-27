from pydantic import BaseModel, Field
from typing import List, Optional

CURRENT_FEATURE_SCHEMA_VERSION = "v1.1"

MODEL_FEATURES = [
    "loss_mean_30s",
    "tx_dropped_max",
    "control_plane_rtt_ms",
    "rx_bytes_slope",
    "tx_bytes_rate",
]

class ModelMetadata(BaseModel):
    model_version: str
    feature_schema_version: str
    feature_names: List[str] = Field(default_factory=lambda: MODEL_FEATURES)
    training_data_hash: Optional[str] = None
    training_commit: Optional[str] = None
    decision_threshold: float = 0.5
    calibration_version: Optional[str] = "platt_v1"
    creation_time: str
    data_origin: str = "synthetic"
