from datetime import datetime, timedelta
from data_pipeline.feature_engineering import FeaturePipeline
from ml.schema import MODEL_FEATURES

def test_training_serving_feature_parity():
    """
    Assert that the FeaturePipeline produces identical feature vectors
    given the same raw telemetry sequence, verifying training-serving parity.
    """
    pipeline1 = FeaturePipeline(window_seconds=30.0, min_samples=3)
    pipeline2 = FeaturePipeline(window_seconds=30.0, min_samples=3)

    base_time = datetime(2026, 1, 1, 12, 0, 0)
    samples = [
        {
            "rx_bytes": 10000.0 + i * 2000.0,
            "tx_bytes": 20000.0 + i * 4000.0,
            "control_plane_rtt_ms": 12.0 + (i % 3),
            "tx_dropped": float(i),
            "loss_percent": 0.05 * i,
            "utilization": 0.2 + 0.05 * i
        }
        for i in range(16)
    ]

    res1 = None
    for i, s in enumerate(samples):
        t = base_time + timedelta(seconds=i * 2)
        res1 = pipeline1.process_raw_telemetry("s1-p1", s, timestamp=t)

    res2 = None
    for i, s in enumerate(samples):
        t = base_time + timedelta(seconds=i * 2)
        res2 = pipeline2.process_raw_telemetry("s1-p1", s, timestamp=t)

    assert res1 is not None and res1.get("status") == "OK"
    assert res2 is not None and res2.get("status") == "OK"

    # Verify all MODEL_FEATURES match exactly
    for feature in MODEL_FEATURES:
        assert feature in res1, f"Missing feature {feature} in pipeline 1"
        assert feature in res2, f"Missing feature {feature} in pipeline 2"
        assert res1[feature] == res2[feature], f"Mismatch for feature {feature}: {res1[feature]} != {res2[feature]}"

    # Verify quality metadata
    assert res1["sample_count"] == 16
    assert res1["coverage_seconds"] == 30.0
    assert res1["reset_detected"] is False
