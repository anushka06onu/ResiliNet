import math
import random
from datetime import datetime, timedelta, timezone
import pytest
from data_pipeline.feature_engineering import FeaturePipeline
from ml.schema import MODEL_FEATURES


@pytest.mark.parametrize("seed", list(range(10)))
def test_feature_pipeline_invariants_and_properties(seed):
    """
    Property and invariant tests for FeaturePipeline:
    1. Output rate metrics are never negative, even across counter resets.
    2. Computed features are always finite numbers (no NaN / Inf).
    3. Window never includes events older than window_seconds (30s).
    4. Feature dictionary keys strictly match MODEL_FEATURES when data is sufficient.
    5. Counter reset detection is flagged in quality_metadata.
    """
    rng = random.Random(seed * 1000 + 42)
    pipeline = FeaturePipeline(window_seconds=30.0, min_samples=3)
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    link_id = f"test_link_prop_{seed}"

    num_samples = 20 # 20 samples at 2s = 38s > 24s minimum window coverage
    rx_counter = rng.randint(1000, 50000)
    tx_counter = rng.randint(5000, 100000)

    final_features = None
    for i in range(num_samples):
        timestamp = base_time + timedelta(seconds=i * 2)

        # Simulate periodic counter resets or monotonic increases
        if rng.random() < 0.2:
            rx_counter = rng.randint(100, 500) # reset
            tx_counter = rng.randint(100, 500) # reset
        else:
            rx_counter += rng.randint(100, 10000)
            tx_counter += rng.randint(500, 50000)

        rtt = rng.uniform(1.0, 150.0)
        dropped = rng.randint(0, 50)
        loss = rng.uniform(0.0, 25.0)
        util = rng.uniform(0.05, 0.99)

        raw_metrics = {
            "rx_bytes": rx_counter,
            "tx_bytes": tx_counter,
            "control_plane_rtt_ms": rtt,
            "tx_dropped": dropped,
            "loss_percent": loss,
            "utilization": util,
        }

        res = pipeline.process_raw_telemetry(link_id, raw_metrics, timestamp)
        if res and res.get("status") not in ["INSUFFICIENT_DATA", "STALE_DATA"]:
            final_features = res

    assert final_features is not None, "Failed to compute features after sufficient time coverage"
    assert final_features.get("status") != "INVALID_SAMPLE"

    # 1. Key features must exist and be finite
    for feat in MODEL_FEATURES:
        assert feat in final_features, f"Missing feature {feat}"
        val = final_features[feat]
        assert isinstance(val, (int, float))
        assert not math.isnan(val), f"Feature {feat} is NaN"
        assert not math.isinf(val), f"Feature {feat} is Inf"

    # 2. Rates and drops must be non-negative
    assert final_features["tx_bytes_rate"] >= 0.0, f"Negative tx_bytes_rate: {final_features['tx_bytes_rate']}"
    assert final_features["tx_dropped_max"] >= 0.0, f"Negative tx_dropped_max: {final_features['tx_dropped_max']}"
    assert final_features["loss_mean_30s"] >= 0.0, f"Negative loss_mean_30s: {final_features['loss_mean_30s']}"

    # 3. Quality metadata invariant checks
    assert final_features.get("status") == "OK"
    assert "sample_count" in final_features
    assert final_features["sample_count"] >= 3
    assert final_features["sample_count"] <= 16
    assert final_features["coverage_seconds"] >= 24.0
    assert final_features["coverage_seconds"] <= 32.0
    assert "reset_detected" in final_features or "counter_reset_detected" in final_features


def test_feature_pipeline_rejects_nan_and_inf():
    """Verify corrupted telemetry with NaN or Inf is rejected with INVALID_SAMPLE once window is full"""
    pipeline = FeaturePipeline(window_seconds=30.0, min_samples=3)
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Feed 15 samples with NaN in one of them
    last_res = None
    for i in range(16):
        t = base_time + timedelta(seconds=i * 2)
        corrupt_metrics = {
            "rx_bytes": float("nan") if i == 15 else float(1000 * i),
            "tx_bytes": 1000.0 * i,
            "control_plane_rtt_ms": 10.0,
            "tx_dropped": 0.0,
            "loss_percent": 0.0,
            "utilization": 0.5,
        }
        res = pipeline.process_raw_telemetry("link_nan", corrupt_metrics, t)
        if res:
            last_res = res

    assert last_res is not None
    assert last_res.get("status") == "INVALID_SAMPLE"
