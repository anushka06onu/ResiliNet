"""
Dataset and Telemetry Quality Validator
Enforces physical plausibility, temporal monotonicity, counter consistency,
and ML training feature validity across recorded telemetry and training datasets.
"""

from typing import List, Tuple
import numpy as np
import pandas as pd
from ml.schema import MODEL_FEATURES


def validate_raw_telemetry(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Validates raw telemetry against physical and temporal network constraints:
    1. Required columns (timestamp, rx_bytes, tx_bytes).
    2. Finite numeric values (no NaN or Inf).
    3. Monotonic non-duplicate timestamps per link/port stream.
    4. Monotonic cumulative byte counters (unless marked as reset).
    5. Non-negative packet drop counts.
    6. Loss percentage bounded within [0.0, 100.0].
    7. Plausible control plane RTT (> 0.0 ms and <= 5000.0 ms).
    8. Canonical utilization ratio bounded within [0.0, 1.0].
    """
    violations: List[str] = []

    if df.empty:
        return False, ["Dataset is empty"]

    required_columns = ["timestamp", "rx_bytes", "tx_bytes"]
    for col in required_columns:
        if col not in df.columns:
            violations.append(f"Missing required column: {col}")

    if violations:
        return False, violations

    # Check for NaN / infinite values in numeric fields
    numeric_cols = [c for c in df.columns if c != "timestamp" and pd.api.types.is_numeric_dtype(df[c])]
    for col in numeric_cols:
        series_clean = df[col].dropna()
        if len(series_clean) < len(df[col]):
            violations.append(f"Column '{col}' contains {len(df[col]) - len(series_clean)} NaN values")
        if not np.isfinite(series_clean).all():
            violations.append(f"Column '{col}' contains non-finite (Inf/-Inf) values")

    # Group-level temporal and counter consistency
    group_cols = [c for c in ["experiment_id", "switch_id", "port_no", "link_id"] if c in df.columns]
    grouped = df.groupby(group_cols) if group_cols else [(None, df)]

    for name, group in grouped:
        group_label = str(name) if name is not None else "global"

        # 1. Unique timestamps within stream
        if group["timestamp"].duplicated().any():
            dup_count = group["timestamp"].duplicated().sum()
            violations.append(f"Duplicate timestamps ({dup_count} duplicates) in group: {group_label}")

        # 2. Monotonic non-decreasing timestamps
        ts = pd.to_datetime(group["timestamp"])
        if not ts.is_monotonic_increasing:
            violations.append(f"Timestamps are not strictly non-decreasing in group: {group_label}")

        # 3. Monotonic byte counters (unless reset event explicitly marked on that row)
        reset = group["counter_reset"].fillna(False).astype(bool) if "counter_reset" in group.columns else pd.Series(False, index=group.index)
        rx_diff = group["rx_bytes"].diff()
        tx_diff = group["tx_bytes"].diff()

        invalid_rx = (rx_diff < 0) & ~reset
        invalid_tx = (tx_diff < 0) & ~reset

        if invalid_rx.dropna().any():
            neg_rx = invalid_rx.sum()
            violations.append(f"Decreasing rx_bytes ({neg_rx} instances without reset marker) in group: {group_label}")
        if invalid_tx.dropna().any():
            neg_tx = invalid_tx.sum()
            violations.append(f"Decreasing tx_bytes ({neg_tx} instances without reset marker) in group: {group_label}")

        # 4. Non-negative drop counts
        if "tx_dropped" in group.columns:
            neg_drops = (group["tx_dropped"] < 0).sum()
            if neg_drops > 0:
                violations.append(f"Negative tx_dropped ({neg_drops} rows) in group: {group_label}")

        # 5. Loss percentage range [0.0, 100.0]
        if "loss_percent" in group.columns:
            out_of_bounds = ((group["loss_percent"] < 0.0) | (group["loss_percent"] > 100.0)).sum()
            if out_of_bounds > 0:
                violations.append(f"Loss percent out of bounds [0, 100] ({out_of_bounds} rows) in group: {group_label}")

        # 6. Plausible RTT (RTT > 0.0 ms and RTT <= 5000.0 ms)
        if "control_plane_rtt_ms" in group.columns:
            implausible_rtt = ((group["control_plane_rtt_ms"] <= 0.0) | (group["control_plane_rtt_ms"] > 5000.0)).sum()
            if implausible_rtt > 0:
                violations.append(f"Implausible RTT <= 0 or > 5000ms ({implausible_rtt} rows) in group: {group_label}")

        # 7. Canonical utilization ratio range [0.0, 1.0]
        if "utilization" in group.columns:
            util_out_of_bounds = ((group["utilization"] < 0.0) | (group["utilization"] > 1.0)).sum()
            if util_out_of_bounds > 0:
                violations.append(f"Utilization ratio out of valid physical range [0.0, 1.0] ({util_out_of_bounds} rows) in group: {group_label}")

    is_valid = len(violations) == 0
    return is_valid, violations


def validate_feature_dataset(df: pd.DataFrame, target_col: str = "sla_violated_in_horizon") -> Tuple[bool, List[str]]:
    """
    Validates an engineered ML dataset prior to model training:
    1. Presence of all required MODEL_FEATURES.
    2. Presence and binary validity of target column ({0, 1}).
    3. Complete absence of NaN / Inf values across all features.
    4. Warm-up row exclusion (no placeholder rows from insufficient window data).
    5. Experiment ID boundary tracking.
    """
    violations: List[str] = []

    if df.empty:
        return False, ["Dataset is empty"]

    # 1. Check feature columns
    for feat in MODEL_FEATURES:
        if feat not in df.columns:
            violations.append(f"Missing required model feature: {feat}")

    if violations:
        # Cannot inspect missing columns
        return False, violations

    # 2. Check target column validity
    if target_col not in df.columns:
        violations.append(f"Missing target column: {target_col}")
    else:
        unique_targets = set(df[target_col].dropna().unique())
        if not unique_targets.issubset({0, 1, 0.0, 1.0}):
            violations.append(f"Target column '{target_col}' contains invalid non-binary classes: {unique_targets}")

    # 3. Check for finite values
    for feat in MODEL_FEATURES:
        feat_series = df[feat]
        if feat_series.isna().any():
            violations.append(f"Feature '{feat}' contains {feat_series.isna().sum()} NaN values")
        if not np.isfinite(feat_series.dropna()).all():
            violations.append(f"Feature '{feat}' contains infinite values")

    # 4. Check warm-up row exclusion (insufficient window rows typically produce all-zero or null rate/slope)
    if "status" in df.columns:
        invalid_status_rows = (df["status"] != "OK").sum()
        if invalid_status_rows > 0:
            violations.append(f"Dataset contains {invalid_status_rows} unready/warm-up status rows")

    # 5. Check experiment_id presence
    if "experiment_id" not in df.columns:
        violations.append("Missing 'experiment_id' column for experiment boundary tracking")

    is_valid = len(violations) == 0
    return is_valid, violations


# Backward compatibility alias
validate_telemetry_dataframe = validate_raw_telemetry
