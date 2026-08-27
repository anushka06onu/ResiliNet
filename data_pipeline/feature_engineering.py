from collections import defaultdict
from datetime import datetime
import numpy as np

class FeaturePipeline:
    """
    Shared pipeline for computing ML features from raw telemetry.
    Ensures identical feature calculation between training data generation
    and live serving to prevent skew.
    """
    def __init__(self, history_limit=15):
        # 15 intervals of 2 seconds = 30 seconds
        self.history_limit = history_limit
        self.link_history = defaultdict(list)
        
    def process_raw_telemetry(self, link_id, raw_metrics, timestamp=None):
        """
        raw_metrics should contain:
        - rx_bytes
        - tx_bytes
        - control_plane_rtt_ms
        - tx_dropped
        - loss_percent
        - utilization
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
            
        history = self.link_history[link_id]
        
        # Append new raw metrics
        entry = {
            "timestamp": timestamp,
            "metrics": raw_metrics
        }
        history.append(entry)
        
        # Trim history
        if len(history) > self.history_limit:
            history.pop(0)
            
        # Calculate features over the window
        return self._compute_features(history)
        
    def _compute_features(self, history):
        if not history:
            return {}
            
        # Extract series
        loss_series = [h["metrics"].get("loss_percent", 0.0) for h in history]
        tx_dropped_series = [h["metrics"].get("tx_dropped", 0) for h in history]
        rx_bytes_series = [h["metrics"].get("rx_bytes", 0) for h in history]
        
        # Compute aggregates
        loss_mean_30s = sum(loss_series) / len(loss_series)
        tx_dropped_max = max(tx_dropped_series)
        
        # Slope of rx_bytes
        rx_bytes_slope = 0.0
        if len(rx_bytes_series) > 1:
            rx_bytes_slope = rx_bytes_series[-1] - rx_bytes_series[0]
            
        # Rate of tx_bytes between last two ticks
        tx_bytes_rate = 0.0
        if len(history) > 1:
            t1 = history[-2]["timestamp"].timestamp()
            t2 = history[-1]["timestamp"].timestamp()
            dt = t2 - t1
            if dt > 0:
                tx_bytes_rate = (history[-1]["metrics"].get("tx_bytes", 0) - history[-2]["metrics"].get("tx_bytes", 0)) / dt
                
        # Current latest values for passthrough
        latest = history[-1]["metrics"]
                
        return {
            "loss_mean_30s": loss_mean_30s,
            "tx_dropped_max": tx_dropped_max,
            "control_plane_rtt_ms": latest.get("control_plane_rtt_ms", 0.0),
            "rx_bytes_slope": rx_bytes_slope,
            "tx_bytes_rate": tx_bytes_rate,
            "utilization": latest.get("utilization", 0.0)
        }
