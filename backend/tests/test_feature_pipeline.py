import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from data_pipeline.feature_engineering import FeaturePipeline


def test_feature_pipeline_insufficient_data():
    pipeline = FeaturePipeline()
    
    metrics = {
        "rx_bytes": 1000,
        "tx_bytes": 1000,
        "tx_dropped": 0,
        "tx_errors": 0,
        "latency_ms": 10.0,
        "control_plane_rtt_ms": 10.0
    }
    
    # 1st sample
    res1 = pipeline.process_raw_telemetry("s1-s2", metrics, timestamp=datetime.fromtimestamp(1.0))
    assert res1.get("status") == "INSUFFICIENT_DATA"
    
    # 2nd sample
    res2 = pipeline.process_raw_telemetry("s1-s2", metrics, timestamp=datetime.fromtimestamp(2.0))
    assert res2.get("status") == "INSUFFICIENT_DATA"
    
    # 3rd sample
    res3 = pipeline.process_raw_telemetry("s1-s2", metrics, timestamp=datetime.fromtimestamp(3.0))
    assert res3.get("status") != "INSUFFICIENT_DATA"
    assert "control_plane_rtt_ms" in res3
