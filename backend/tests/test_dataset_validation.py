import numpy as np
import pandas as pd
import pytest
from data_pipeline.validate_dataset import validate_raw_telemetry, validate_feature_dataset


def test_validate_telemetry_dataframe_clean():
    clean_df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01 12:00:00", periods=20, freq="2s"),
        "experiment_id": ["exp_1"] * 20,
        "switch_id": ["s1"] * 20,
        "port_no": [1] * 20,
        "rx_bytes": [1000 * (i + 1) for i in range(20)],
        "tx_bytes": [5000 * (i + 1) for i in range(20)],
        "control_plane_rtt_ms": [12.5 + i * 0.1 for i in range(20)],
        "tx_dropped": [0] * 20,
        "loss_percent": [0.1] * 20,
        "utilization": [0.45] * 20,
    })

    is_valid, violations = validate_raw_telemetry(clean_df)
    assert is_valid is True
    assert len(violations) == 0


def test_validate_telemetry_dataframe_detects_violations():
    corrupted_df = pd.DataFrame({
        # Out-of-order timestamp
        "timestamp": [
            "2026-01-01 12:00:10",
            "2026-01-01 12:00:05", # inversion
            "2026-01-01 12:00:20"
        ],
        "experiment_id": ["exp_corrupt"] * 3,
        "rx_bytes": [100, 200, 300],
        "tx_bytes": [100, 200, 300],
        # Negative drops
        "tx_dropped": [-5, 0, 1],
        # Out of bounds loss
        "loss_percent": [150.0, 0.0, 0.0],
        # Negative RTT
        "control_plane_rtt_ms": [-10.0, 15.0, 20.0],
    })

    is_valid, violations = validate_raw_telemetry(corrupted_df)
    assert is_valid is False
    assert any("Timestamps are not strictly non-decreasing" in v for v in violations)
    assert any("Negative tx_dropped" in v for v in violations)
    assert any("Loss percent out of bounds" in v for v in violations)
    assert any("Implausible RTT" in v for v in violations)


def test_validate_feature_dataset_clean_and_corrupt():
    clean_feature_df = pd.DataFrame({
        "experiment_id": ["exp_1"] * 10,
        "loss_mean_30s": [0.1] * 10,
        "tx_dropped_max": [0] * 10,
        "control_plane_rtt_ms": [10.0] * 10,
        "rx_bytes_slope": [50.0] * 10,
        "tx_bytes_rate": [500.0] * 10,
        "sla_violated_in_horizon": [0] * 8 + [1] * 2,
    })
    is_valid, violations = validate_feature_dataset(clean_feature_df)
    assert is_valid is True
    assert len(violations) == 0

    # Test missing feature
    missing_col_df = pd.DataFrame({
        "experiment_id": ["exp_1"] * 3,
        "loss_mean_30s": [0.1, 0.2, 0.3],
        "tx_dropped_max": [0, 0, 0],
        "control_plane_rtt_ms": [10.0, 12.0, 15.0],
        "rx_bytes_slope": [50.0, 60.0, 70.0],
        "sla_violated_in_horizon": [0, 1, 0],
    })
    is_valid, violations = validate_feature_dataset(missing_col_df)
    assert is_valid is False
    assert any("Missing required model feature: tx_bytes_rate" in v for v in violations)

    # Test corrupted with NaN / Inf and non-binary class
    corrupt_feature_df = pd.DataFrame({
        "experiment_id": ["exp_1"] * 3,
        "loss_mean_30s": [0.1, np.inf, 0.2],
        "tx_dropped_max": [0, 0, 0],
        "control_plane_rtt_ms": [10.0, 12.0, np.nan],
        "rx_bytes_slope": [50.0, 60.0, 70.0],
        "tx_bytes_rate": [500.0, 600.0, 700.0],
        "sla_violated_in_horizon": [0, 1, 2], # invalid class 2
    })
    is_valid, violations = validate_feature_dataset(corrupt_feature_df)
    assert is_valid is False
    assert any("contains infinite values" in v for v in violations)
    assert any("contains 1 NaN values" in v for v in violations)
    assert any("invalid non-binary classes" in v for v in violations)


def test_validate_telemetry_dataframe_sample_real_run():
    """Validate that the checked-in sample_real_run telemetry adheres to physical constraints."""
    from pathlib import Path
    telemetry_path = Path(__file__).resolve().parents[2] / "experiments" / "sample_real_run" / "telemetry.csv"
    if telemetry_path.exists():
        df = pd.read_csv(telemetry_path)
        is_valid, violations = validate_raw_telemetry(df)
        assert is_valid is True, f"Sample real run failed validation: {violations}"
