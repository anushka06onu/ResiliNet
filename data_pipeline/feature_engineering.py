from collections import defaultdict
from datetime import datetime, timedelta, timezone

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
            timestamp = datetime.now(timezone.utc)

        history = self.link_history[link_id]


        # Enforce out-of-order sample policy
        if history and timestamp <= history[-1]["timestamp"]:
            return {"status": "STALE_DATA", "message": "Out of order metric dropped"}

        # Append new raw metrics
        entry = {
            "timestamp": timestamp,
            "metrics": raw_metrics
        }
        history.append(entry)

        # Global Trim: Trim history for ALL links by time window
        cutoff_time = timestamp - timedelta(seconds=self.window_seconds)
        expired_links = []
        for l_id, l_hist in self.link_history.items():
            pruned = [h for h in l_hist if h["timestamp"] >= cutoff_time]
            if len(pruned) == 0:
                expired_links.append(l_id)
            else:
                self.link_history[l_id] = pruned

        for l_id in expired_links:
            del self.link_history[l_id]

        if link_id not in self.link_history:
            return {"status": "INSUFFICIENT_DATA"}

        history = self.link_history[link_id]

        # Check if we have enough time coverage (at least 80% of window)
        time_coverage = (history[-1]["timestamp"] - history[0]["timestamp"]).total_seconds()
        if time_coverage < (self.window_seconds * 0.8):
            return {"status": "INSUFFICIENT_DATA"}

        # Calculate features over the window
        return self._compute_features(history)

    def _compute_features(self, history):
        if len(history) < self.min_samples:
            return {"status": "INSUFFICIENT_DATA"}

        # Validate that no metrics have invalid/NaN floats
        def _parse_strict_float(val, name):
            if val is None:
                return None
            try:
                f_val = float(val)
                if np.isnan(f_val) or np.isinf(f_val):
                    return None
                return f_val
            except (ValueError, TypeError):
                return None

        # Check latest values
        latest = history[-1]["metrics"]
        for key in ["rx_bytes", "tx_bytes", "control_plane_rtt_ms", "tx_dropped", "loss_percent", "utilization"]:
            if _parse_strict_float(latest.get(key), key) is None:
                return {"status": "INVALID_SAMPLE", "message": f"Invalid or missing float for metric {key}"}

        loss_series = []
        for h in history:
            val = _parse_strict_float(h["metrics"].get("loss_percent"), "loss_percent")
            if val is None:
                return {"status": "INVALID_SAMPLE", "message": "Invalid float in loss_percent history"}
            loss_series.append(val)

        reset_detected = False

        # Compute counter differences safely (handling wraparounds/resets)
        def _get_diff(series):
            nonlocal reset_detected
            diffs = []
            for i in range(1, len(series)):
                diff = series[i] - series[i-1]
                if diff < 0:
                    reset_detected = True
                    diff = series[i]
                diffs.append(diff)
            return diffs

        tx_dropped_raw = []
        for h in history:
            val = _parse_strict_float(h["metrics"].get("tx_dropped"), "tx_dropped")
            if val is None:
                return {"status": "INVALID_SAMPLE", "message": "Invalid float in tx_dropped history"}
            tx_dropped_raw.append(val)
        tx_dropped_diffs = _get_diff(tx_dropped_raw)

        rx_bytes_raw = []
        for h in history:
            val = _parse_strict_float(h["metrics"].get("rx_bytes"), "rx_bytes")
            if val is None:
                return {"status": "INVALID_SAMPLE", "message": "Invalid float in rx_bytes history"}
            rx_bytes_raw.append(val)
        rx_bytes_diffs = _get_diff(rx_bytes_raw)

        tx_bytes_raw = []
        for h in history:
            val = _parse_strict_float(h["metrics"].get("tx_bytes"), "tx_bytes")
            if val is None:
                return {"status": "INVALID_SAMPLE", "message": "Invalid float in tx_bytes history"}
            tx_bytes_raw.append(val)
        tx_bytes_diffs = _get_diff(tx_bytes_raw)

        # Compute aggregates
        loss_mean_30s = float(np.mean(loss_series))
        tx_dropped_max = float(np.max(tx_dropped_diffs)) if tx_dropped_diffs else 0.0

        # Slope of rx_bytes (linear regression over time)
        timestamps = np.array([h["timestamp"].timestamp() for h in history])
        t_centered = timestamps - timestamps[0]
        time_coverage = float(t_centered[-1])

        rx_bytes_slope = 0.0
        if len(rx_bytes_raw) > 1 and t_centered[-1] > 0:
            cum_rx = np.concatenate(([0], np.cumsum(rx_bytes_diffs)))
            if len(t_centered) == len(cum_rx):
                slope, _ = np.polyfit(t_centered, cum_rx, 1)
                rx_bytes_slope = float(slope)

        tx_bytes_rate = 0.0
        if len(history) > 1:
            dt = t_centered[-1] - t_centered[-2]
            if dt > 0 and len(tx_bytes_diffs) > 0:
                tx_bytes_rate = float(tx_bytes_diffs[-1] / dt)

        age_ms = 0.0
        if len(history) > 1:
            age_ms = float((history[-1]["timestamp"] - history[-2]["timestamp"]).total_seconds() * 1000)

        return {
            "status": "OK",
            "sample_count": len(history),
            "coverage_seconds": round(time_coverage, 2),
            "latest_sample_age_ms": round(age_ms, 2),
            "reset_detected": reset_detected,
            "loss_mean_30s": loss_mean_30s,
            "tx_dropped_max": tx_dropped_max,
            "control_plane_rtt_ms": float(latest.get("control_plane_rtt_ms", 0.0)),
            "rx_bytes_slope": rx_bytes_slope,
            "tx_bytes_rate": tx_bytes_rate,
            "utilization": float(latest.get("utilization", 0.0))
        }
