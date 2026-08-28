#!/usr/bin/env python3
"""
ResiliNet Empirical Campaign Evaluation & Statistical Metrics Aggregator.

Performs rigorous scholarship-grade statistical evaluation across routing policies:
- Strict bidirectional SHA256 integrity verification (with path containment checks)
- Exact 60-run matrix validation (4 scenarios x 3 policies x 5 seeds) with missing/duplicate/unexpected reports
- Campaign invariant fingerprint consistency verification
- Strict eligibility filtering (excluding mock, partial, or unverified runs to excluded_runs.csv)
- Data quality exception tracking (to data_quality_issues.csv)
- Episode-, flow-, and link-matched event timing (warning lead time, reroute latency, SLA recovery, SLA violation duration)
- Student's t-distribution 95% Confidence Intervals with per-metric sample size and missing counts
- Paired-policy comparisons across all metrics (Cohen's dz, paired t-intervals)
- Full ML predictive performance validation (Precision, Recall, Specificity, F1, PR-AUC, ROC-AUC, Brier score, False-Alert Rate)
- Pure strict JSON serialization (NaN/Infinity -> null)
"""

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

import numpy as np
import pandas as pd
from scipy import stats


def load_campaign_spec(project_root: Path) -> Dict[str, Any]:
    """Loads campaign specification from campaign.yaml or fallback defaults."""
    yaml_path = project_root / "experiments" / "campaign.yaml"
    if yaml_path.exists():
        try:
            import yaml
            with open(yaml_path, "r") as yf:
                return yaml.safe_load(yf)
        except Exception:
            pass
    return {
        "scenarios": ["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"],
        "policies": ["static", "reactive", "predictive"],
        "seeds": [42, 43, 44, 45, 46],
        "duration_seconds": 60,
        "required_runs": 60
    }


def sanitize_for_json(obj: Any) -> Any:
    """Recursively converts NaN, Infinity, and numpy scalars into strict standard JSON-compliant types."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, (np.floating, np.integer)):
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x) for x in obj]
    return obj


def verify_directory_checksums(exp_dir: Path) -> Tuple[bool, Optional[str]]:
    """
    Verifies every file against SHA256SUMS in the run directory.
    Enforces bidirectional completeness and strict path containment.
    """
    sums_path = exp_dir / "SHA256SUMS"
    if not sums_path.exists():
        return False, "SHA256SUMS missing"

    exp_resolved = exp_dir.resolve()
    checksummed_files: Set[Path] = set()

    try:
        with open(sums_path, "r") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    return False, f"Malformed checksum line {line_no}: '{line}'"
                expected_hash, rel_name = parts
                rel_name = rel_name.strip()

                # Path containment check against directory traversal
                if ".." in rel_name:
                    return False, f"Path traversal attempt in checksum line: '{rel_name}'"

                target_file = (exp_dir / rel_name).resolve()
                if not (target_file == exp_resolved or exp_resolved in target_file.parents):
                    return False, f"File {rel_name} escapes experiment root {exp_dir}"

                if not target_file.exists() or not target_file.is_file():
                    return False, f"File {rel_name} recorded in SHA256SUMS is missing"

                h = hashlib.sha256()
                with open(target_file, "rb") as fl:
                    for chunk in iter(lambda: fl.read(65536), b""):
                        h.update(chunk)
                if h.hexdigest() != expected_hash:
                    return False, f"SHA-256 hash mismatch for {rel_name}"

                checksummed_files.add(target_file)

        # Bidirectional check: ensure all files in exp_dir are accounted for in SHA256SUMS
        for p in exp_dir.rglob("*"):
            if p.is_file() and p != sums_path and not p.name.startswith("."):
                if p.resolve() not in checksummed_files:
                    return False, f"Unchecksummed artifact found: {p.relative_to(exp_dir)}"

        return True, None
    except Exception as e:
        return False, f"Checksum verification exception: {e}"


def parse_ping_latency(ping_file: Path, errors_list: List[dict]) -> Dict[str, Optional[float]]:
    """Parses min/avg/max/mdev from ping output text."""
    if not ping_file.exists():
        return {"rtt_min_ms": np.nan, "rtt_avg_ms": np.nan, "rtt_max_ms": np.nan, "rtt_mdev_ms": np.nan}
    try:
        content = ping_file.read_text()
        match = re.search(r"rtt min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms", content)
        if match:
            return {
                "rtt_min_ms": float(match.group(1)),
                "rtt_avg_ms": float(match.group(2)),
                "rtt_max_ms": float(match.group(3)),
                "rtt_mdev_ms": float(match.group(4))
            }
    except Exception as exc:
        errors_list.append({"artifact": ping_file.name, "error": str(exc)})
    return {"rtt_min_ms": np.nan, "rtt_avg_ms": np.nan, "rtt_max_ms": np.nan, "rtt_mdev_ms": np.nan}


def parse_iperf_log(log_path: Path, errors_list: List[dict]) -> Dict[str, Optional[float]]:
    """Parses bandwidth, jitter, and loss percentage from an iperf server/client log."""
    if not log_path.exists():
        return {"throughput_mbps": np.nan, "jitter_ms": np.nan, "packet_loss_pct": np.nan}

    try:
        content = log_path.read_text()
        if not content.strip():
            return {"throughput_mbps": np.nan, "jitter_ms": np.nan, "packet_loss_pct": np.nan}

        # Match UDP server report: 0.0-60.0 sec  14.3 MBytes  2.00 Mbits/sec  0.045 ms 0/10200 (0%)
        match_udp = re.findall(r"([\d\.]+)\s+Mbits/sec\s+([\d\.]+)\s+ms\s+\d+/\d+\s+\(([\d\.]+)%\)", content)
        if match_udp:
            last = match_udp[-1]
            return {
                "throughput_mbps": float(last[0]),
                "jitter_ms": float(last[1]),
                "packet_loss_pct": float(last[2])
            }

        # Match TCP or client throughput
        match_tp = re.findall(r"([\d\.]+)\s+Mbits/sec", content)
        if match_tp:
            return {
                "throughput_mbps": float(match_tp[-1]),
                "jitter_ms": np.nan,
                "packet_loss_pct": np.nan
            }
    except Exception as exc:
        errors_list.append({"artifact": log_path.name, "error": str(exc)})

    return {"throughput_mbps": np.nan, "jitter_ms": np.nan, "packet_loss_pct": np.nan}


def parse_event_timing_episodes(exp_dir: Path, errors_list: List[dict]) -> Dict[str, Any]:
    """
    Parses events.jsonl with episode-, flow-, and link-matched timing calculations:
    - Warning lead time: sla_violation_started - prediction_threshold_crossed
    - Reroute latency: reroute_verified_at - reroute_started
    - Recovery time: sla_recovered - sla_violation_started
    - SLA violation duration: sla_recovered - sla_violation_started
    - Unrecovered episode count
    """
    res = {
        "warning_lead_time_s": np.nan,
        "reroute_latency_s": np.nan,
        "recovery_time_s": np.nan,
        "violation_duration_s": np.nan,
        "total_violation_duration_s": 0.0,
        "unrecovered_episodes_count": 0,
        "reroute_started_count": 0,
        "reroute_verified_successes": 0,
        "rollback_count": 0
    }

    events_path = exp_dir / "events.jsonl"
    if not events_path.exists():
        return res

    try:
        events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    except Exception as exc:
        errors_list.append({"artifact": "events.jsonl", "error": str(exc)})
        return res

    episodes: Dict[str, Dict[str, Any]] = {}

    for ev in events:
        ev_name = ev.get("event")
        ep_id = ev.get("episode_id") or f"{ev.get('link_id')}_{ev.get('flow_id')}"
        ts_str = ev.get("timestamp")
        if not ts_str:
            continue
        ts = pd.to_datetime(ts_str)

        if ep_id not in episodes:
            episodes[ep_id] = {
                "pred_cross": None,
                "violation_start": None,
                "reroute_start": None,
                "reroute_verified": None,
                "sla_recovered": None,
                "rollbacks": 0
            }

        ep = episodes[ep_id]
        if ev_name == "prediction_threshold_crossed" and ep["pred_cross"] is None:
            ep["pred_cross"] = ts
        elif ev_name == "sla_violation_started" and ep["violation_start"] is None:
            ep["violation_start"] = ts
        elif ev_name == "reroute_started":
            ep["reroute_start"] = ts
            res["reroute_started_count"] += 1
        elif ev_name == "reroute_verified_at":
            ep["reroute_verified"] = ts
            res["reroute_verified_successes"] += 1
        elif ev_name == "rollback_completed":
            ep["rollbacks"] += 1
            res["rollback_count"] += 1
        elif ev_name == "sla_recovered" and ep["sla_recovered"] is None:
            ep["sla_recovered"] = ts

    lead_times = []
    reroute_latencies = []
    recovery_times = []
    violation_durations = []
    unrecovered_count = 0

    for ep_id, ep in episodes.items():
        # Warning lead time
        if ep["pred_cross"] is not None and ep["violation_start"] is not None:
            if ep["violation_start"] >= ep["pred_cross"]:
                lead_times.append((ep["violation_start"] - ep["pred_cross"]).total_seconds())

        # Reroute latency
        if ep["reroute_start"] is not None and ep["reroute_verified"] is not None:
            if ep["reroute_verified"] >= ep["reroute_start"]:
                reroute_latencies.append((ep["reroute_verified"] - ep["reroute_start"]).total_seconds())

        # Recovery time & violation duration
        if ep["violation_start"] is not None:
            if ep["sla_recovered"] is not None:
                if ep["sla_recovered"] >= ep["violation_start"]:
                    dur = (ep["sla_recovered"] - ep["violation_start"]).total_seconds()
                    recovery_times.append(dur)
                    violation_durations.append(dur)
            else:
                unrecovered_count += 1

    if lead_times:
        res["warning_lead_time_s"] = float(np.mean(lead_times))
    if reroute_latencies:
        res["reroute_latency_s"] = float(np.mean(reroute_latencies))
    if recovery_times:
        res["recovery_time_s"] = float(np.mean(recovery_times))
    if violation_durations:
        res["violation_duration_s"] = float(np.mean(violation_durations))
        res["total_violation_duration_s"] = float(np.sum(violation_durations))
    res["unrecovered_episodes_count"] = unrecovered_count

    return res


def parse_run_directory(exp_dir: Path, quality_errors: List[dict]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """
    Parses a single experiment directory with complete provenance, checksums, and traffic parsing.
    Returns (record, None) if eligible, or (None, exclusion_reason) if excluded.
    """
    manifest_path = exp_dir / "manifest.json"
    if not manifest_path.exists():
        return None, {"experiment_id": exp_dir.name, "reason": "manifest.json missing"}

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:
        quality_errors.append({"experiment_id": exp_dir.name, "artifact": "manifest.json", "error": str(e)})
        return None, {"experiment_id": exp_dir.name, "reason": f"manifest.json corrupt: {e}"}

    exp_id = manifest.get("experiment_id", exp_dir.name)
    scenario = manifest.get("scenario")
    effective_policy = manifest.get("effective_policy")
    seed = manifest.get("seed")

    # Eligibility filters
    if not manifest.get("real_experiment", False):
        return None, {"experiment_id": exp_id, "reason": "Not a real experiment (mock data)"}

    if manifest.get("data_origin") != "mininet":
        return None, {"experiment_id": exp_id, "reason": f"Invalid data origin: {manifest.get('data_origin')}"}

    if manifest.get("status") != "completed":
        return None, {"experiment_id": exp_id, "reason": f"Experiment status not completed: {manifest.get('status')}"}

    if not manifest.get("evidence_complete", False):
        return None, {"experiment_id": exp_id, "reason": "Evidence collection incomplete"}

    if not manifest.get("eligible_for_analysis", True):
        return None, {"experiment_id": exp_id, "reason": "Declared not eligible for analysis"}

    # Policy sync and backend finalization success
    policy_sync = manifest.get("policy_sync", {})
    if policy_sync.get("required") and not policy_sync.get("successful"):
        return None, {"experiment_id": exp_id, "reason": "Backend policy sync failed"}

    backend_fin = manifest.get("backend_finalization", {})
    if backend_fin.get("required") and not backend_fin.get("successful"):
        return None, {"experiment_id": exp_id, "reason": "Backend finalization failed"}

    # Bidirectional Checksum Verification
    chk_ok, chk_err = verify_directory_checksums(exp_dir)
    if not chk_ok:
        quality_errors.append({"experiment_id": exp_id, "artifact": "SHA256SUMS", "error": chk_err})
        return None, {"experiment_id": exp_id, "reason": f"Checksum verification failed: {chk_err}"}

    traffic_dir = exp_dir / "traffic"

    # Ping parsing
    ping_after = parse_ping_latency(traffic_dir / "ping_after.txt", quality_errors)

    # Iperf overall parsing
    iperf_data = parse_iperf_log(traffic_dir / "iperf_server.log", quality_errors)

    # Critical flow parsing
    crit_ping = parse_ping_latency(traffic_dir / "critical_ping.txt", quality_errors)
    crit_iperf = parse_iperf_log(traffic_dir / "critical_iperf_server.log", quality_errors)

    # Telemetry parsing for control-plane RTT and loss
    tel_file = exp_dir / "telemetry.csv"
    control_plane_rtt = np.nan
    tel_loss_mean = np.nan
    if tel_file.exists():
        try:
            df_tel = pd.read_csv(tel_file)
            if "control_plane_rtt_ms" in df_tel.columns:
                control_plane_rtt = float(df_tel["control_plane_rtt_ms"].dropna().mean())
            if "loss_percent" in df_tel.columns:
                tel_loss_mean = float(df_tel["loss_percent"].dropna().mean())
        except Exception as exc:
            quality_errors.append({"experiment_id": exp_id, "artifact": "telemetry.csv", "error": str(exc)})

    # Event timing parsing
    event_metrics = parse_event_timing_episodes(exp_dir, quality_errors)

    # Routing decisions metrics
    dec_file = exp_dir / "routing_decisions.jsonl"
    total_decisions = 0
    installed_decisions = 0
    if dec_file.exists():
        try:
            decisions = [json.loads(line) for line in dec_file.read_text().splitlines() if line.strip()]
            total_decisions = len(decisions)
            installed_decisions = sum(1 for d in decisions if d.get("outcome_status") == "SUCCESS")
        except Exception as exc:
            quality_errors.append({"experiment_id": exp_id, "artifact": "routing_decisions.jsonl", "error": str(exc)})

    # Packet loss resolution
    pkt_loss = iperf_data.get("packet_loss_pct")
    if pd.isna(pkt_loss) or pkt_loss is None:
        pkt_loss = tel_loss_mean

    record = {
        "experiment_id": exp_id,
        "scenario": scenario,
        "effective_policy": effective_policy,
        "seed": seed,
        "packet_loss_pct": pkt_loss,
        "end_to_end_rtt_ms": ping_after.get("rtt_avg_ms"),
        "control_plane_rtt_ms": control_plane_rtt,
        "throughput_mbps": iperf_data.get("throughput_mbps"),
        "jitter_ms": iperf_data.get("jitter_ms"),
        "critical_packet_loss_pct": crit_iperf.get("packet_loss_pct"),
        "critical_rtt_ms": crit_ping.get("rtt_avg_ms"),
        "critical_throughput_mbps": crit_iperf.get("throughput_mbps"),
        "warning_lead_time_s": event_metrics["warning_lead_time_s"],
        "reroute_latency_s": event_metrics["reroute_latency_s"],
        "recovery_time_s": event_metrics["recovery_time_s"],
        "violation_duration_s": event_metrics["violation_duration_s"],
        "total_violation_duration_s": event_metrics["total_violation_duration_s"],
        "unrecovered_episodes_count": event_metrics["unrecovered_episodes_count"],
        "reroute_started_count": event_metrics["reroute_started_count"],
        "reroute_verified_successes": event_metrics["reroute_verified_successes"],
        "rollback_count": event_metrics["rollback_count"],
        "total_routing_decisions": total_decisions,
        "campaign_invariant_fingerprint": manifest.get("campaign_invariant_fingerprint"),
        "run_config_fingerprint": manifest.get("run_config_fingerprint")
    }

    return record, None


def compute_student_t_stats(series: pd.Series) -> Dict[str, Any]:
    """Computes mean, sample standard deviation, and Student's t 95% confidence intervals."""
    clean = series.dropna().astype(float)
    n = len(clean)
    missing = len(series) - n

    if n == 0:
        return {
            "mean": np.nan, "std_dev": np.nan,
            "ci95_lower": np.nan, "ci95_upper": np.nan,
            "n": 0, "missing": missing
        }

    mean_val = float(clean.mean())
    if n == 1:
        return {
            "mean": round(mean_val, 3), "std_dev": np.nan,
            "ci95_lower": round(mean_val, 3), "ci95_upper": round(mean_val, 3),
            "n": 1, "missing": missing
        }

    std_val = float(clean.std(ddof=1))
    t_crit = float(stats.t.ppf(0.975, df=n - 1))
    margin = t_crit * (std_val / math.sqrt(n)) if std_val > 0 else 0.0

    return {
        "mean": round(mean_val, 3),
        "std_dev": round(std_val, 3),
        "ci95_lower": round(mean_val - margin, 3),
        "ci95_upper": round(mean_val + margin, 3),
        "n": n,
        "missing": missing
    }


def compute_paired_differences(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Computes rigorous paired differences across policy pairs (seed-by-seed):
    - predictive vs reactive
    - predictive vs static
    Includes paired Student's t 95% CI and Cohen's dz.
    """
    metrics = [
        "packet_loss_pct",
        "end_to_end_rtt_ms",
        "throughput_mbps",
        "critical_packet_loss_pct",
        "critical_throughput_mbps",
        "violation_duration_s",
        "recovery_time_s",
        "warning_lead_time_s"
    ]

    comparisons = [
        ("predictive", "reactive", "predictive_vs_reactive"),
        ("predictive", "static", "predictive_vs_static")
    ]

    paired_results = []

    for scenario, sc_group in df.groupby("scenario"):
        for base_pol, comp_pol, comp_name in comparisons:
            df_base = sc_group[sc_group["effective_policy"] == base_pol].set_index("seed")
            df_comp = sc_group[sc_group["effective_policy"] == comp_pol].set_index("seed")

            common_seeds = sorted(list(set(df_base.index).intersection(set(df_comp.index))))
            if not common_seeds:
                continue

            for m in metrics:
                if m not in df_base.columns or m not in df_comp.columns:
                    continue

                diffs = []
                for s in common_seeds:
                    val_b = df_base.loc[s, m]
                    val_c = df_comp.loc[s, m]
                    if pd.notna(val_b) and pd.notna(val_c):
                        diffs.append(float(val_b - val_c))

                n = len(diffs)
                if n < 2:
                    continue

                mean_d = float(np.mean(diffs))
                std_d = float(np.std(diffs, ddof=1))

                # Confidence interval on paired difference
                t_crit = float(stats.t.ppf(0.975, df=n - 1))
                margin = t_crit * (std_d / math.sqrt(n)) if std_d > 0 else 0.0

                # Cohen's dz calculation
                if std_d > 0:
                    cohens_dz = round(mean_d / std_d, 2)
                else:
                    cohens_dz = None

                paired_results.append({
                    "scenario": scenario,
                    "comparison": comp_name,
                    "metric": m,
                    "paired_n": n,
                    "mean_difference": round(mean_d, 3),
                    "std_difference": round(std_d, 3),
                    "ci95_lower": round(mean_d - margin, 3),
                    "ci95_upper": round(mean_d + margin, 3),
                    "cohens_dz": cohens_dz
                })

    return paired_results


def evaluate_predictive_ml_performance(results_dir: Path, df_valid: pd.DataFrame) -> Dict[str, Any]:
    """
    Evaluates ML model predictive performance by performing as-of time/link alignment:
    Prediction at time t on link L -> Observed telemetry on link L near t + forecast_horizon_s (10s)
    Ground truth: SLA violation determined from runtime SLA latency/loss thresholds.
    Calculates TP, TN, FP, FN, Precision, Recall, Specificity, F1, ROC-AUC, PR-AUC, Brier score, False Alert Rate.
    Saves aligned table to prediction_ground_truth_alignment.csv.
    """
    # Read configured SLA thresholds
    max_latency = 20.0
    max_loss = 1.0
    forecast_horizon_s = 10.0
    time_tolerance_s = 4.0

    try:
        from backend.app.config import sla_config
        max_latency = float(sla_config.max_latency_ms)
        max_loss = float(sla_config.max_loss_percent)
    except Exception:
        try:
            from app.config import sla_config
            max_latency = float(sla_config.max_latency_ms)
            max_loss = float(sla_config.max_loss_percent)
        except Exception:
            pass

    aligned_records = []

    for _, row in df_valid[df_valid["effective_policy"] == "predictive"].iterrows():
        exp_id = row["experiment_id"]
        exp_dir = results_dir / exp_id
        pred_file = exp_dir / "predictions.csv"
        tel_file = exp_dir / "telemetry.csv"

        if pred_file.exists() and tel_file.exists():
            try:
                df_p = pd.read_csv(pred_file)
                df_t = pd.read_csv(tel_file)

                if "timestamp" in df_p.columns and "congestion_probability" in df_p.columns and "timestamp" in df_t.columns:
                    df_p["ts"] = pd.to_datetime(df_p["timestamp"])
                    df_t["ts"] = pd.to_datetime(df_t["timestamp"])

                    # Build telemetry link identifier
                    if "link_id" not in df_t.columns:
                        if "switch_id" in df_t.columns and "port_no" in df_t.columns:
                            df_t["link_id"] = df_t["switch_id"].astype(str) + "-p" + df_t["port_no"].astype(str)
                        else:
                            df_t["link_id"] = "default_link"

                    # Normalize predictions link identifier
                    if "link_id" not in df_p.columns:
                        df_p["link_id"] = "default_link"

                    # Perform strict same-link matched as-of time join
                    for _, p_row in df_p.iterrows():
                        t_pred = p_row["ts"]
                        p_link = str(p_row["link_id"])
                        p_prob = float(p_row["congestion_probability"])
                        t_target = t_pred + pd.Timedelta(seconds=forecast_horizon_s)

                        # Match telemetry ONLY on the exact same link near target horizon time
                        link_tel = df_t[
                            (df_t["link_id"] == p_link) &
                            (df_t["ts"] >= t_target - pd.Timedelta(seconds=time_tolerance_s)) &
                            (df_t["ts"] <= t_target + pd.Timedelta(seconds=time_tolerance_s))
                        ]
                        if link_tel.empty:
                            # Strict requirement: no cross-link fallback permitted
                            continue

                        obs_row = link_tel.iloc[0]
                        obs_loss = float(obs_row.get("loss_percent", 0.0))
                        obs_rtt = float(obs_row.get("control_plane_rtt_ms", 0.0))
                        is_violation_actual = bool(obs_loss > max_loss or obs_rtt > max_latency)

                        aligned_records.append({
                            "experiment_id": exp_id,
                            "prediction_timestamp": p_row["timestamp"],
                            "link_id": p_link,
                            "predicted_probability": p_prob,
                            "predicted_label": int(p_prob >= 0.5),
                            "forecast_horizon_seconds": forecast_horizon_s,
                            "observed_timestamp": str(obs_row["timestamp"]),
                            "observed_loss_percent": obs_loss,
                            "observed_rtt_ms": obs_rtt,
                            "future_observed_violation": int(is_violation_actual)
                        })
            except Exception:
                pass

    if not aligned_records:
        return {
            "predictive_performance_validated": False,
            "sample_size": 0,
            "reason": "no_aligned_prediction_telemetry_pairs",
            "note": "No aligned prediction-telemetry pairs found"
        }

    df_aligned = pd.DataFrame(aligned_records)
    aligned_path = results_dir / "prediction_ground_truth_alignment.csv"
    df_aligned.to_csv(aligned_path, index=False)

    y_true_arr = df_aligned["future_observed_violation"].values
    y_prob_arr = df_aligned["predicted_probability"].values
    y_pred_arr = df_aligned["predicted_label"].values

    tp = int(np.sum((y_true_arr == 1) & (y_pred_arr == 1)))
    tn = int(np.sum((y_true_arr == 0) & (y_pred_arr == 0)))
    fp = int(np.sum((y_true_arr == 0) & (y_pred_arr == 1)))
    fn = int(np.sum((y_true_arr == 1) & (y_pred_arr == 0)))

    precision = round(tp / (tp + fp), 3) if (tp + fp) > 0 else np.nan
    recall = round(tp / (tp + fn), 3) if (tp + fn) > 0 else np.nan
    specificity = round(tn / (tn + fp), 3) if (tn + fp) > 0 else np.nan
    f1 = round(2 * precision * recall / (precision + recall), 3) if (pd.notna(precision) and pd.notna(recall) and (precision + recall) > 0) else np.nan
    false_alert_rate = round(fp / (tn + fp), 3) if (tn + fp) > 0 else np.nan
    missed_event_rate = round(fn / (tp + fn), 3) if (tp + fn) > 0 else np.nan
    brier_score = round(float(np.mean((y_prob_arr - y_true_arr) ** 2)), 4)

    # Compute ROC-AUC and PR-AUC with strict multi-class validation
    roc_auc = None
    pr_auc = None
    auc_note = None
    pr_auc_error = None

    unique_classes = np.unique(y_true_arr)
    has_both_classes = bool(len(unique_classes) >= 2 and np.sum(y_true_arr == 1) > 0 and np.sum(y_true_arr == 0) > 0)

    if has_both_classes:
        try:
            from sklearn.metrics import roc_auc_score, average_precision_score
            roc_auc = round(float(roc_auc_score(y_true_arr, y_prob_arr)), 3)
            pr_auc = round(float(average_precision_score(y_true_arr, y_prob_arr)), 3)
        except Exception as e:
            try:
                # Rank-based ROC-AUC fallback
                n_pos = np.sum(y_true_arr == 1)
                n_neg = np.sum(y_true_arr == 0)
                ranks = stats.rankdata(y_prob_arr)
                sum_pos_ranks = np.sum(ranks[y_true_arr == 1])
                u_stat = sum_pos_ranks - n_pos * (n_pos + 1) / 2.0
                roc_auc = round(float(u_stat / (n_pos * n_neg)), 3)
            except Exception:
                pass
            pr_auc = None
            pr_auc_error = f"scikit-learn average_precision_score calculation unavailable: {e}"
    else:
        auc_note = f"Single-class ground truth observed in dataset (classes: {unique_classes.tolist()}). Both positive and negative instances required."

    # Validation criteria: must have both classes, valid alignment, and positive sample count
    is_validated = bool(has_both_classes and len(y_true_arr) >= 2)

    result_dict = {
        "predictive_performance_validated": is_validated,
        "sample_size": len(y_true_arr),
        "true_positives": tp,
        "true_negatives": tn,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1_score": f1,
        "false_alert_rate": false_alert_rate,
        "missed_event_rate": missed_event_rate,
        "brier_score": brier_score,
        "roc_auc": roc_auc,
        "pr_auc": pr_auc
    }
    if not is_validated and not has_both_classes:
        result_dict["reason"] = "single_class_ground_truth"
    if auc_note:
        result_dict["auc_note"] = auc_note
    if pr_auc_error:
        result_dict["pr_auc_error"] = pr_auc_error

    return result_dict


def evaluate_campaign(results_dir: Path, allow_incomplete: bool = False) -> Dict[str, Any]:
    """
    Main evaluation pipeline:
    1. Scans all experiment subdirectories
    2. Validates campaign invariant fingerprint consistency
    3. Verifies SHA256 integrity and parses network & ML metrics
    4. Validates 60-run matrix completeness
    5. Outputs aggregated metrics, paired comparisons, and statistical reports
    """
    project_root = Path(__file__).resolve().parents[1]
    campaign_spec = load_campaign_spec(project_root)

    expected_scenarios = campaign_spec.get("scenarios", ["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"])
    expected_policies = campaign_spec.get("policies", ["static", "reactive", "predictive"])
    expected_seeds = campaign_spec.get("seeds", [42, 43, 44, 45, 46])

    valid_records: List[Dict[str, Any]] = []
    excluded_records: List[Dict[str, str]] = []
    quality_errors: List[dict] = []

    for d in sorted(results_dir.iterdir()):
        if d.is_dir() and (d / "manifest.json").exists():
            rec, excl = parse_run_directory(d, quality_errors)
            if rec:
                valid_records.append(rec)
            else:
                excluded_records.append(excl)

    # Save excluded runs and quality issues reports
    df_excl = pd.DataFrame(excluded_records)
    excl_path = results_dir / "excluded_runs.csv"
    df_excl.to_csv(excl_path, index=False)

    df_quality = pd.DataFrame(quality_errors)
    quality_path = results_dir / "data_quality_issues.csv"
    df_quality.to_csv(quality_path, index=False)

    # Campaign Invariant Fingerprint Consistency Check
    observed_fps = {r.get("campaign_invariant_fingerprint") for r in valid_records if r.get("campaign_invariant_fingerprint")}
    fp_consistent = (len(observed_fps) <= 1)

    # Matrix Completeness Validation
    expected_combinations = {
        (scenario, policy, seed)
        for scenario in expected_scenarios
        for policy in expected_policies
        for seed in expected_seeds
    }

    observed_combinations = set()
    duplicate_records = []
    unexpected_records = []

    for rec in valid_records:
        key = (rec["scenario"], rec["effective_policy"], rec["seed"])
        if key in observed_combinations:
            duplicate_records.append({"scenario": key[0], "policy": key[1], "seed": key[2], "experiment_id": rec["experiment_id"]})
        else:
            observed_combinations.add(key)

        if key not in expected_combinations:
            unexpected_records.append({"scenario": key[0], "policy": key[1], "seed": key[2], "experiment_id": rec["experiment_id"]})

    missing_combinations = expected_combinations - observed_combinations
    missing_records = [{"scenario": k[0], "policy": k[1], "seed": k[2]} for k in sorted(missing_combinations)]

    # Write matrix integrity reports
    pd.DataFrame(missing_records).to_csv(results_dir / "missing_combinations.csv", index=False)
    pd.DataFrame(duplicate_records).to_csv(results_dir / "duplicate_combinations.csv", index=False)
    pd.DataFrame(unexpected_records).to_csv(results_dir / "unexpected_combinations.csv", index=False)

    is_complete_matrix = (
        len(valid_records) == len(expected_combinations) and
        len(missing_combinations) == 0 and
        len(duplicate_records) == 0 and
        len(unexpected_records) == 0 and
        fp_consistent
    )

    if not is_complete_matrix and not allow_incomplete:
        raise RuntimeError(
            f"Campaign matrix validation failed: {len(missing_combinations)} missing, "
            f"{len(duplicate_records)} duplicates, {len(unexpected_records)} unexpected out of {len(expected_combinations)} expected runs. "
            f"Pass --allow-incomplete to generate preliminary tables."
        )

    if not valid_records:
        print("No eligible completed Mininet runs found for campaign evaluation.")
        return {"eligible_runs": 0, "excluded_runs": len(df_excl), "matrix_complete": False}

    df_valid = pd.DataFrame(valid_records)
    runs_path = results_dir / "campaign_runs.csv"
    df_valid.to_csv(runs_path, index=False)

    # Statistical Aggregations by (scenario, effective_policy)
    aggregated = []
    metrics_to_aggregate = [
        "packet_loss_pct",
        "end_to_end_rtt_ms",
        "control_plane_rtt_ms",
        "throughput_mbps",
        "critical_packet_loss_pct",
        "critical_throughput_mbps",
        "reroute_verified_successes",
        "warning_lead_time_s",
        "recovery_time_s",
        "violation_duration_s"
    ]

    for (scenario, policy), group in df_valid.groupby(["scenario", "effective_policy"]):
        row = {
            "scenario": scenario,
            "policy": policy,
            "group_total_runs": len(group)
        }
        for m in metrics_to_aggregate:
            stats_m = compute_student_t_stats(group[m])
            row[f"{m}_mean"] = stats_m["mean"]
            row[f"{m}_std"] = stats_m["std_dev"]
            row[f"{m}_ci95_lower"] = stats_m["ci95_lower"]
            row[f"{m}_ci95_upper"] = stats_m["ci95_upper"]
            row[f"{m}_n"] = stats_m["n"]
            row[f"{m}_missing"] = stats_m["missing"]
        aggregated.append(row)

    df_agg = pd.DataFrame(aggregated)
    agg_path = results_dir / "aggregated_metrics.csv"
    df_agg.to_csv(agg_path, index=False)

    # Paired Policy Comparisons
    paired_diffs = compute_paired_differences(df_valid)
    df_paired = pd.DataFrame(paired_diffs)
    paired_path = results_dir / "paired_policy_comparisons.csv"
    df_paired.to_csv(paired_path, index=False)

    # ML Predictive Performance Evaluation
    ml_perf = evaluate_predictive_ml_performance(results_dir, df_valid)
    ml_path = results_dir / "prediction_metrics.json"
    with open(ml_path, "w") as mf:
        json.dump(sanitize_for_json(ml_perf), mf, indent=2)

    # Clean Strict JSON Summary
    summary_raw = {
        "evaluated_at": pd.Timestamp.utcnow().isoformat(),
        "preliminary": not is_complete_matrix,
        "campaign_matrix_complete": is_complete_matrix,
        "expected_matrix_size": len(expected_combinations),
        "eligible_runs_count": len(df_valid),
        "excluded_runs_count": len(df_excl),
        "missing_combinations_count": len(missing_combinations),
        "duplicate_combinations_count": len(duplicate_records),
        "unexpected_combinations_count": len(unexpected_records),
        "fingerprint_consistent": fp_consistent,
        "scenarios": df_valid["scenario"].unique().tolist(),
        "policies": df_valid["effective_policy"].unique().tolist(),
        "predictive_ml_evaluation": ml_perf,
        "paired_comparisons": paired_diffs,
        "aggregated_metrics": aggregated
    }

    summary_sanitized = sanitize_for_json(summary_raw)
    summary_path = results_dir / "campaign_summary.json"
    with open(summary_path, "w") as jf:
        json.dump(summary_sanitized, jf, indent=2)

    print(f"Aggregated statistical summary written to {agg_path}")
    print(f"Paired comparison metrics written to {paired_path}")
    print(f"ML evaluation written to {ml_path}")
    print(f"Campaign summary written to {summary_path}")

    return {
        "eligible_runs": len(df_valid),
        "excluded_runs": len(df_excl),
        "matrix_complete": is_complete_matrix
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ResiliNet Campaign Statistical Evaluation")
    parser.add_argument("--results-dir", type=str, default="experiments/results", help="Results directory")
    parser.add_argument("--allow-incomplete", action="store_true", help="Allow processing incomplete campaign matrices")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    res_path = Path(args.results_dir) if Path(args.results_dir).is_absolute() else project_root / args.results_dir
    res_path.mkdir(parents=True, exist_ok=True)
    evaluate_campaign(res_path, allow_incomplete=args.allow_incomplete)
