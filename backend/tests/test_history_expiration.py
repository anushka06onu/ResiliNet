import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from data_pipeline.feature_engineering import FeaturePipeline

def test_history_expiration():
    pipeline = FeaturePipeline(window_seconds=30.0)
    
    now = datetime.utcnow()
    past = now - timedelta(seconds=40)
    
    # Process old telemetry for link1
    pipeline.process_raw_telemetry("link1", {"rx_bytes": 10}, timestamp=past)
    
    # Now process for link2 at the current time
    pipeline.process_raw_telemetry("link2", {"rx_bytes": 20}, timestamp=now)
    
    # link1 should have been pruned entirely (it's 40 seconds old and window is 30)
    assert "link1" not in pipeline.link_history
    
    # link2 should exist
    assert "link2" in pipeline.link_history
