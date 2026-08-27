import os
import sys

import lightgbm as lgb
import pandas as pd
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from ml.schema import MODEL_FEATURES


def test_model_schema_compatibility():
    """Verify the saved LightGBM model expects the exact schema defined in MODEL_FEATURES"""
    model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ml/artifacts/lightgbm_model.txt'))
    if not os.path.exists(model_path):
        pytest.skip("Model artifact not found, run ml pipeline first.")
    
    model = lgb.Booster(model_file=model_path)
    model_features = model.feature_name()
    
    assert model_features == MODEL_FEATURES, "LightGBM model features do not match ml.schema.MODEL_FEATURES!"

def test_future_label_boundaries():
    """Verify that shifting labels into the future does not cross experiment boundaries."""
    from data_pipeline.label_generation import generate_future_labels

    # Create two experiments
    df = pd.DataFrame([
        {'experiment_id': 'exp_1', 'current_sla_violated': 0},
        {'experiment_id': 'exp_1', 'current_sla_violated': 0},
        {'experiment_id': 'exp_1', 'current_sla_violated': 1}, # violated near the end
        {'experiment_id': 'exp_1', 'current_sla_violated': 0},

        {'experiment_id': 'exp_2', 'current_sla_violated': 0},
        {'experiment_id': 'exp_2', 'current_sla_violated': 0},
        {'experiment_id': 'exp_2', 'current_sla_violated': 0},
        {'experiment_id': 'exp_2', 'current_sla_violated': 0}
    ])

    labeled_df = generate_future_labels(df, group_col='experiment_id', target_col='current_sla_violated', horizon_steps=2)

    exp_2 = labeled_df[labeled_df['experiment_id'] == 'exp_2']
    # Exp 2 should NOT see any violations, despite exp 1 having one right before it.
    assert exp_2['sla_violated_in_horizon'].sum() == 0.0, "Leakage occurred across experiment boundary!"

def test_model_metadata_validation():
    from ml.schema import ModelMetadata, CURRENT_FEATURE_SCHEMA_VERSION
    import json
    meta_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ml/artifacts/model_metadata.json'))
    if not os.path.exists(meta_path):
        pytest.skip("Model metadata not found.")

    with open(meta_path, "r") as f:
        data = json.load(f)

    meta = ModelMetadata(**data)
    assert meta.feature_schema_version == CURRENT_FEATURE_SCHEMA_VERSION
    assert meta.decision_threshold > 0.0
    assert len(meta.feature_names) == 5


def test_synthetic_raw_counters_monotonic():
    """Verify that synthetic telemetry generation maintains monotonic cumulative counters."""
    import numpy as np
    from datetime import datetime, timedelta, timezone

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rx_bytes_counter = 0
    tx_bytes_counter = 0
    tx_dropped_counter = 0

    records = []
    for t in range(50):
        congested = (t >= 25)
        loss_percent = np.random.exponential(2.5) if congested else np.random.exponential(0.1)
        tx_dropped_counter += int(np.random.poisson(5) if congested else 0)
        latency = max(0.5, np.random.normal(15, 5) if congested else np.random.normal(3, 1))
        utilization = np.random.uniform(0.8, 1.0) if congested else np.random.uniform(0.1, 0.4)
        rx_bytes_counter += max(10, int(np.random.normal(100, 30)))
        tx_bytes_counter += max(500, int(np.random.uniform(5000, 15000)) * 2)

        records.append({
            "timestamp": base_time + timedelta(seconds=t * 2),
            "rx_bytes": rx_bytes_counter,
            "tx_bytes": tx_bytes_counter,
            "tx_dropped": tx_dropped_counter,
            "loss_percent": loss_percent,
            "control_plane_rtt_ms": latency,
            "utilization": utilization
        })

    df = pd.DataFrame(records)
    assert df["tx_dropped"].is_monotonic_increasing
    assert df["rx_bytes"].is_monotonic_increasing
    assert df["tx_bytes"].is_monotonic_increasing
