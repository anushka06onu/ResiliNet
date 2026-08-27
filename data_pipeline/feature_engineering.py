from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np

class FeaturePipeline:
    """
    Shared pipeline for computing ML features from raw telemetry.
    Ensures identical feature calculation between training data generation
    and live serving to prevent skew.
    """
    def __init__(self, window_seconds=30.0, min_samples=3):
        self.window_seconds = window_seconds
        self.min_samples = min_samples
        self.link_history = defaultdict(list)

    def process_raw_telemetry(self, link_id, raw_metrics, timestamp=None):
        """
        raw_metrics should contain:
        - rx_bytes (cumulative)
        - tx_bytes (cumulative)
        - control_plane_rtt_ms
        - tx_dropped (cumulative)
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

        # Trim history by time window
        cutoff_time = timestamp - timedelta(seconds=self.window_seconds)
        self.link_history[link_id] = [h for h in history if h["timestamp"] >= cutoff_time]
        history = self.link_history[link_id]

        # Calculate features over the window
        return self._compute_features(history)

    def _compute_features(self, history):
        if len(history) < self.min_samples:
            return {"status": "INSUFFICIENT_DATA"}

        # Extract series
        loss_series = [h["metrics"].get("loss_percent", 0.0) for h in history]

        # Compute counter differences safely (handling wraparounds/resets)
        def _get_diff(series):
            diffs = []
            for i in range(1, len(series)):
                diff = series[i] - series[i-1]
                if diff < 0: # Handle reset or wraparound
                    diff = series[i]
                diffs.append(diff)
            return diffs

        tx_dropped_raw = [h["metrics"].get("tx_dropped", 0) for h in history]
        tx_dropped_diffs = _get_diff(tx_dropped_raw)

        rx_bytes_raw = [h["metrics"].get("rx_bytes", 0) for h in history]
        rx_bytes_diffs = _get_diff(rx_bytes_raw)

        tx_bytes_raw = [h["metrics"].get("tx_bytes", 0) for h in history]
        tx_bytes_diffs = _get_diff(tx_bytes_raw)

        # Compute aggregates
        loss_mean_30s = float(np.mean(loss_series))
        tx_dropped_max = float(np.max(tx_dropped_diffs)) if tx_dropped_diffs else 0.0

        # Slope of rx_bytes (linear regression over time)
        timestamps = np.array([h["timestamp"].timestamp() for h in history])
        # Center timestamps for numerical stability
        t_centered = timestamps - timestamps[0]

        rx_bytes_slope = 0.0
        if len(rx_bytes_raw) > 1 and t_centered[-1] > 0:
            # Linear regression: y = mx + c
            # We regress the cumulative rx_bytes over time to find bytes/sec slope
            # If counters reset, we should use cumulative sum of diffs instead of raw
            cum_rx = np.concatenate(([0], np.cumsum(rx_bytes_diffs)))
            if len(t_centered) == len(cum_rx):
                slope, _ = np.polyfit(t_centered, cum_rx, 1)
                rx_bytes_slope = float(slope)

        # Rate of tx_bytes between last two ticks
        tx_bytes_rate = 0.0
        if len(history) > 1:
            dt = t_centered[-1] - t_centered[-2]
            if dt > 0 and len(tx_bytes_diffs) > 0:
                tx_bytes_rate = float(tx_bytes_diffs[-1] / dt)

        # Current latest values for passthrough
        latest = history[-1]["metrics"]

        return {
            "status": "OK",
            "loss_mean_30s": loss_mean_30s,
            "tx_dropped_max": tx_dropped_max,
            "control_plane_rtt_ms": latest.get("control_plane_rtt_ms", 0.0),
            "rx_bytes_slope": rx_bytes_slope,
            "tx_bytes_rate": tx_bytes_rate,
            "utilization": latest.get("utilization", 0.0)
        }
