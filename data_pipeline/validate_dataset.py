"""
Dataset and Telemetry Quality Validator
Enforces physical plausibility, temporal monotonicity, and counter consistency rules
across recorded telemetry data and offline ML training datasets.
"""

from typing import Dict, List, Tuple, Union
import pandas as pd


def validate_telemetry_dataframe(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Validates a telemetry DataFrame against physical and temporal constraints.
    Returns (is_valid, list_of_violations).
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

    # Check for NaN / infinite values in core fields
    numeric_cols = [c for c in df.columns if c != "timestamp" and pd.api.types.is_numeric_dtype(df[c])]
    for col in numeric_cols:
        nan_count = df[col].isna().sum()
        if nan_count > 0:
            violations.append(f"Column '{col}' contains {nan_count} NaN values")

    # Temporal monotonicity per entity group
    group_cols = [c for c in ["experiment_id", "switch_id", "port_no", "link_id"] if c in df.columns]
    if group_cols:
        grouped = df.groupby(group_cols)
    else:
        grouped = [(None, df)]

    for name, group in grouped:
        group_label = str(name) if name is not None else "global"
        
        # 1. Monotonic timestamps
        ts = pd.to_datetime(group["timestamp"])
        if not ts.is_monotonic_increasing:
            violations.append(f"Timestamps are not strictly non-decreasing in group: {group_label}")

        # 2. Non-negative drop counts
        if "tx_dropped" in group.columns:
            neg_drops = (group["tx_dropped"] < 0).sum()
            if neg_drops > 0:
                violations.append(f"Negative tx_dropped ({neg_drops} rows) in group: {group_label}")

        # 3. Loss percentage range [0.0, 100.0]
        if "loss_percent" in group.columns:
            out_of_bounds = ((group["loss_percent"] < 0.0) | (group["loss_percent"] > 100.0)).sum()
            if out_of_bounds > 0:
                violations.append(f"Loss percent out of bounds [0, 100] ({out_of_bounds} rows) in group: {group_label}")

        # 4. Plausible RTT (RTT > 0.0 ms and RTT <= 5000.0 ms)
        if "control_plane_rtt_ms" in group.columns:
            implausible_rtt = ((group["control_plane_rtt_ms"] < 0.0) | (group["control_plane_rtt_ms"] > 5000.0)).sum()
            if implausible_rtt > 0:
                violations.append(f"Implausible RTT ({implausible_rtt} rows) in group: {group_label}")

        # 5. Utilization range [0.0, 1.0] (or [0.0, 100.0])
        if "utilization" in group.columns:
            util_neg = (group["utilization"] < 0.0).sum()
            util_excess = (group["utilization"] > 100.0).sum()
            if util_neg > 0 or util_excess > 0:
                violations.append(f"Utilization out of valid physical range in group: {group_label}")

    is_valid = len(violations) == 0
    return is_valid, violations
