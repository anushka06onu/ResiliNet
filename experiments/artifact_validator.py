#!/usr/bin/env python3
"""
Centralized Artifact Validation and Fingerprinting Module for ResiliNet.
Enforces rigorous validation rules, schema compliance, row count accounting,
and cryptographic campaign invariant fingerprinting.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd

from network.routing.policies import normalize_policy


REQUIRED_TELEMETRY_COLUMNS = [
    "timestamp", "experiment_id", "switch_id", "port_no",
    "rx_bytes", "tx_bytes", "control_plane_rtt_ms",
    "tx_dropped", "loss_percent", "utilization"
]

REQUIRED_PREDICTION_COLUMNS = [
    "timestamp", "link_id", "congestion_probability", "is_violation_predicted"
]


def get_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 digest of a file."""
    if not filepath.exists():
        return "missing"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_campaign_invariant_fingerprint(project_root: Path) -> Dict[str, str]:
    """
    Computes the campaign invariant fingerprint that must be IDENTICAL across all 60 campaign runs:
    - Git commit
    - Model SHA256 & run ID
    - Topology SHA256
    - Ryu Controller code SHA256
    - Predictive Router code SHA256
    - SLA decision thresholds
    """
    git_commit = "unknown"
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=True)
        git_commit = res.stdout.strip()
    except Exception:
        pass

    model_path = project_root / "ml" / "artifacts" / "lightgbm_model.txt"
    topo_path = project_root / "frontend" / "public" / "topology.json"
    ryu_path = project_root / "network" / "controller" / "resilinet_ryu.py"
    router_path = project_root / "network" / "routing" / "predictive_routing.py"

    model_hash = get_file_sha256(model_path)
    topo_hash = get_file_sha256(topo_path)
    ryu_hash = get_file_sha256(ryu_path)
    router_hash = get_file_sha256(router_path)

    components = {
        "git_commit": git_commit,
        "model_sha256": model_hash,
        "topology_sha256": topo_hash,
        "ryu_controller_sha256": ryu_hash,
        "predictive_router_sha256": router_hash,
        "decision_threshold": 0.5,
        "sampling_interval_s": 2,
        "forecast_horizon_s": 10
    }

    raw_str = "|".join(f"{k}:{v}" for k, v in sorted(components.items()))
    fingerprint_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

    return {
        "fingerprint": fingerprint_hash,
        "components": components
    }


def compute_run_config_fingerprint(scenario: str, policy: str, seed: int, duration: int, params: Optional[dict] = None) -> str:
    """Computes the run-specific configuration fingerprint."""
    canon_policy = normalize_policy(policy)
    param_str = json.dumps(params or {}, sort_keys=True)
    raw = f"scenario:{scenario}|policy:{canon_policy}|seed:{seed}|duration:{duration}|params:{param_str}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def validate_finalized_artifacts(run_dir: Path, policy: str, mode: str = "REAL") -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Performs comprehensive schema, row-count, and semantic verification of all run artifacts.
    Returns (is_valid, validation_report, error_list).
    """
    canon_policy = normalize_policy(policy)
    errors: List[str] = []

    report = {
        "telemetry_valid": False,
        "telemetry_rows": 0,
        "predictions_valid": False,
        "prediction_rows": 0,
        "routing_decisions_valid": False,
        "routing_decision_rows": 0,
        "events_valid": False,
        "event_rows": 0,
        "evidence_report_valid": False,
        "switches_valid": False,
        "traffic_valid": False,
        "scenario_parameters_valid": False,
        "all_valid": False
    }

    # 1. Telemetry validation
    tel_file = run_dir / "telemetry.csv"
    if not tel_file.exists() or tel_file.stat().st_size == 0:
        errors.append("telemetry.csv is missing or empty")
    else:
        try:
            df_tel = pd.read_csv(tel_file)
            missing_cols = [c for c in REQUIRED_TELEMETRY_COLUMNS if c not in df_tel.columns]
            if missing_cols:
                errors.append(f"telemetry.csv missing columns: {missing_cols}")
            elif len(df_tel) < 1:
                errors.append("telemetry.csv contains 0 data rows")
            else:
                report["telemetry_valid"] = True
                report["telemetry_rows"] = len(df_tel)
        except Exception as e:
            errors.append(f"telemetry.csv parsing error: {e}")

    # 2. Predictions validation
    pred_file = run_dir / "predictions.csv"
    if not pred_file.exists():
        errors.append("predictions.csv is missing")
    else:
        try:
            df_pred = pd.read_csv(pred_file)
            missing_cols = [c for c in REQUIRED_PREDICTION_COLUMNS if c not in df_pred.columns]
            if missing_cols:
                errors.append(f"predictions.csv missing columns: {missing_cols}")
            else:
                if canon_policy == "predictive" and len(df_pred) < 1:
                    errors.append("predictions.csv contains 0 data rows in predictive mode")
                else:
                    report["predictions_valid"] = True
                    report["prediction_rows"] = len(df_pred)
        except Exception as e:
            errors.append(f"predictions.csv parsing error: {e}")

    # 3. Routing Decisions validation (0 rows valid for static/no_reroute)
    dec_file = run_dir / "routing_decisions.jsonl"
    if not dec_file.exists():
        errors.append("routing_decisions.jsonl is missing")
    else:
        try:
            content = dec_file.read_text()
            lines = [l for l in content.splitlines() if l.strip()]
            dec_count = 0
            valid_syntax = True
            for line_no, line in enumerate(lines, 1):
                try:
                    dec = json.loads(line)
                    if "decision_id" not in dec or "timestamp" not in dec:
                        errors.append(f"routing_decisions.jsonl line {line_no} missing required fields")
                        valid_syntax = False
                        break
                    dec_count += 1
                except Exception as e:
                    errors.append(f"routing_decisions.jsonl line {line_no} invalid JSON: {e}")
                    valid_syntax = False
                    break
            if valid_syntax:
                report["routing_decisions_valid"] = True
                report["routing_decision_rows"] = dec_count
        except Exception as e:
            errors.append(f"routing_decisions.jsonl read error: {e}")

    # 4. Events validation
    events_file = run_dir / "events.jsonl"
    if not events_file.exists() and not (run_dir / "scenario_events.jsonl").exists():
        errors.append("events.jsonl is missing")
    else:
        target_ev = events_file if events_file.exists() else (run_dir / "scenario_events.jsonl")
        try:
            lines = [l for l in target_ev.read_text().splitlines() if l.strip()]
            ev_count = 0
            valid_syntax = True
            for line_no, line in enumerate(lines, 1):
                try:
                    ev = json.loads(line)
                    if "event" not in ev or "timestamp" not in ev:
                        errors.append(f"events.jsonl line {line_no} missing event or timestamp")
                        valid_syntax = False
                        break
                    ev_count += 1
                except Exception as e:
                    errors.append(f"events.jsonl line {line_no} invalid JSON: {e}")
                    valid_syntax = False
                    break
            if valid_syntax and ev_count > 0:
                report["events_valid"] = True
                report["event_rows"] = ev_count
        except Exception as e:
            errors.append(f"events.jsonl read error: {e}")

    # 5. Evidence report validation
    ev_rep_file = run_dir / "evidence_report.json"
    if ev_rep_file.exists():
        try:
            ev_data = json.loads(ev_rep_file.read_text())
            if "stage_before" in ev_data and "stage_after" in ev_data:
                report["evidence_report_valid"] = True
        except Exception as e:
            errors.append(f"evidence_report.json corrupt: {e}")

    # 6. Switches and traffic directory validation
    switches_dir = run_dir / "switches"
    traffic_dir = run_dir / "traffic"

    if switches_dir.exists() and any(switches_dir.iterdir()):
        report["switches_valid"] = True

    if traffic_dir.exists() and any(traffic_dir.iterdir()):
        report["traffic_valid"] = True

    # 7. Scenario parameters validation
    params_file = run_dir / "scenario_parameters.json"
    if params_file.exists():
        try:
            json.loads(params_file.read_text())
            report["scenario_parameters_valid"] = True
        except Exception as e:
            errors.append(f"scenario_parameters.json invalid: {e}")

    is_all_valid = (
        report["telemetry_valid"] and
        report["predictions_valid"] and
        report["routing_decisions_valid"] and
        report["events_valid"] and
        len(errors) == 0
    )
    report["all_valid"] = is_all_valid

    return is_all_valid, report, errors
