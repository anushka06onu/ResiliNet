import sys

filename = "backend/app/main.py"
with open(filename, "r") as f:
    content = f.read()

# Add policy to ExperimentConfig
config_patch = """
class ExperimentConfig(BaseModel):
    scenario: str = "normal"
    duration: int = 60
    seed: int = 42
    policy: str = "predictive"
"""
content = content.replace(
"""class ExperimentConfig(BaseModel):
    scenario: str = "normal"
    duration: int = 60
    seed: int = 42""", config_patch)

# Propagate policy on start
start_patch = """
    if config is None:
        config = ExperimentConfig()
        
    orchestrator.set_policy(config.policy)
        
    if not experiment_manager.start(id, config):
"""
content = content.replace(
"""    if config is None:
        config = ExperimentConfig()
        
    if not experiment_manager.start(id, config):""", start_patch)

# Add is_violation_actual logic
violation_patch = """
    # Append to telemetry history
    tel_record = computed_features.copy()
    tel_record['timestamp'] = last_telemetry_timestamp.isoformat() + "Z"
    tel_record['link_id'] = link_id
    telemetry_history.append(tel_record)

    is_violation_actual = computed_features.get("control_plane_rtt_ms", 0.0) > 50.0

    event = {
        "mode": "LIVE LAB",
        "source": "mininet_ryu",
        "type": "link_telemetry",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "experiment_id": "demo_scenario_001",
        "payload": {
            "link_id": link_id,
            "utilization": round(computed_features.get("utilization", 0.0), 4),
            "latency_ms": computed_features.get("control_plane_rtt_ms"),
            "loss_rate": computed_features.get("loss_mean_30s", 0.0),
            "predicted_risk": None,
            "prediction_status": "unavailable",
            "is_violation_actual": is_violation_actual
        }
    }
"""

content = content.replace(
"""    # Append to telemetry history
    tel_record = computed_features.copy()
    tel_record['timestamp'] = last_telemetry_timestamp.isoformat() + "Z"
    tel_record['link_id'] = link_id
    telemetry_history.append(tel_record)

    event = {
        "mode": "LIVE LAB",
        "source": "mininet_ryu",
        "type": "link_telemetry",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "experiment_id": "demo_scenario_001",
        "payload": {
            "link_id": link_id,
            "utilization": round(computed_features.get("utilization", 0.0), 4),
            "latency_ms": computed_features.get("control_plane_rtt_ms"),
            "loss_rate": computed_features.get("loss_mean_30s", 0.0),
            "predicted_risk": None,
            "prediction_status": "unavailable"
        }
    }""", violation_patch)

with open(filename, "w") as f:
    f.write(content)
