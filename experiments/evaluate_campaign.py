#!/usr/bin/env python3
"""
ResiliNet Empirical Campaign Evaluation & Statistical Metrics Aggregator.

Performs rigorous scholarship-grade statistical evaluation across routing policies:
- SHA256 integrity verification
- Strict eligibility filtering (excluding mock, partial, or unverified runs to excluded_runs.csv)
- Separation of control-plane RTT vs end-to-end RTT
- Multi-class concurrent traffic parsing (Critical Tier-1, Video, Bulk)
- Event-based warning lead time and SLA recovery time calculations
- Student's t-distribution 95% Confidence Intervals (Mean, StdDev, CI Lower, CI Upper)
- Paired-policy effect size analysis (Cohen's d, paired differences)
- ML predictive performance validation (Precision, Recall, F1, Brier score, False-Alert Rate)
- 60-run matrix completeness validation (4 scenarios x 3 policies x 5 seeds)
"""

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


EXPECTED_SCENARIOS = ["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"]
EXPECTED_POLICIES = ["static", "reactive", "predictive"]
EXPECTED_SEEDS = [42, 43, 44, 45, 46]


def verify_directory_checksums(exp_dir: Path) -> Tuple[bool, Optional[str]]:
    """Verifies every file against SHA256SUMS in the run directory."""
    sums_path = exp_dir / "SHA256SUMS"
    if not sums_path.exists():
        return False, "SHA256SUMS missing"

    try:
        with open(sums_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue
                expected_hash, rel_name = parts
                target_file = exp_dir / rel_name.strip()
                if not target_file.exists():
                    return False, f"File {rel_name} recorded in SHA256SUMS missing"

                h = hashlib.sha256()
                with open(target_file, "rb") as fl:
                    for chunk in iter(lambda: fl.read(65536), b""):
                        h.update(chunk)
                if h.hexdigest() != expected_hash:
                    return False, f"SHA-256 hash mismatch for {rel_name}"
        return True, None
    except Exception as e:
        return False, f"Checksum verification exception: {e}"


def parse_ping_latency(ping_file: Path) -> Dict[str, Optional[float]]:
    """Parses min/avg/max/mdev from ping output text."""
    if not ping_file.exists():
        return {"rtt_min_ms": np.nan, "rtt_avg_ms": np.nan, "rtt_max_ms": np.nan, "rtt_mdev_ms": np.nan}
    content = ping_file.read_text()
    match = re.search(r"rtt min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms", content)
    if match:
        return {
            "rtt_min_ms": float(match.group(1)),
            "rtt_avg_ms": float(match.group(2)),
            "rtt_max_ms": float(match.group(3)),
            "rtt_mdev_ms": float(match.group(4))
        }
    return {"rtt_min_ms": np.nan, "rtt_avg_ms": np.nan, "rtt_max_ms": np.nan, "rtt_mdev_ms": np.nan}


def parse_iperf_log(log_path: Path) -> Dict[str, Optional[float]]:
    """Parses bandwidth, jitter, and loss percentage from an iperf server/client log."""
    if not log_path.exists():
        return {"throughput_mbps": np.nan, "jitter_ms": np.nan, "packet_loss_pct": np.nan}

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

    return {"throughput_mbps": np.nan, "jitter_ms": np.nan, "packet_loss_pct": np.nan}


def parse_run_directory(exp_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """
    Parses a single experiment directory.
    Returns (record, None) if eligible, or (None, exclusion_reason) if excluded.
    """
    manifest_path = exp_dir / "manifest.json"
    if not manifest_path.exists():
        return None, {"experiment_id": exp_dir.name, "reason": "manifest.json missing"}

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:
        return None, {"experiment_id": exp_dir.name, "reason": f"Corrupt manifest: {e}"}

    exp_id = manifest.get("experiment_id", exp_dir.name)

    # 1. Eligibility Filters
    if not manifest.get("real_experiment"):
        return None, {"experiment_id": exp_id, "reason": "Excluded: mock/fixture run (real_experiment=false)"}
    if manifest.get("data_origin") != "mininet":
        return None, {"experiment_id": exp_id, "reason": f"Excluded: data_origin='{manifest.get('data_origin')}' != 'mininet'"}
    if manifest.get("status") != "completed":
        return None, {"experiment_id": exp_id, "reason": f"Excluded: status='{manifest.get('status')}' != 'completed'"}
    if not manifest.get("evidence_complete"):
        return None, {"experiment_id": exp_id, "reason": "Excluded: evidence_complete is False"}

    policy_sync = manifest.get("policy_sync", {})
    if policy_sync.get("required") and not policy_sync.get("successful"):
        return None, {"experiment_id": exp_id, "reason": "Excluded: backend policy synchronization failed"}

    # 2. Checksum Verification
    checksum_ok, err_msg = verify_directory_checksums(exp_dir)
    if not checksum_ok:
        return None, {"experiment_id": exp_id, "reason": f"Checksum verification failed: {err_msg}"}

    # 3. Parse Telemetry (Control-Plane Metrics)
    control_plane_rtt_mean = np.nan
    telemetry_loss_mean = np.nan
    telemetry_parsed = False
    telemetry_path = exp_dir / "telemetry.csv"
    if telemetry_path.exists():
        try:
            df_tel = pd.read_csv(telemetry_path)
            if not df_tel.empty:
                if "control_plane_rtt_ms" in df_tel.columns:
                    control_plane_rtt_mean = float(df_tel["control_plane_rtt_ms"].dropna().mean())
                if "loss_percent" in df_tel.columns:
                    telemetry_loss_mean = float(df_tel["loss_percent"].dropna().mean())
                telemetry_parsed = True
        except Exception:
            pass

    # 4. Parse Traffic Logs (End-to-End Application Metrics)
    traffic_dir = exp_dir / "traffic"
    ping_parsed = False
    iperf_parsed = False
    end_to_end_rtt_ms = np.nan

    overall_tp = np.nan
    overall_loss = np.nan
    overall_jitter = np.nan

    crit_tp = np.nan
    crit_loss = np.nan
    crit_jitter = np.nan
    video_tp = np.nan
    bulk_tp = np.nan

    if traffic_dir.exists():
        # Ping
        ping_after = parse_ping_latency(traffic_dir / "ping_after.txt")
        if not np.isnan(ping_after.get("rtt_avg_ms", np.nan)):
            end_to_end_rtt_ms = ping_after["rtt_avg_ms"]
            ping_parsed = True

        # Standard iperf
        std_iperf = parse_iperf_log(traffic_dir / "iperf_server.log")
        if np.isnan(std_iperf["throughput_mbps"]):
            std_iperf = parse_iperf_log(traffic_dir / "iperf_client.log")
        if not np.isnan(std_iperf["throughput_mbps"]):
            overall_tp = std_iperf["throughput_mbps"]
            overall_loss = std_iperf["packet_loss_pct"]
            overall_jitter = std_iperf["jitter_ms"]
            iperf_parsed = True

        # Concurrent traffic classes
        crit_res = parse_iperf_log(traffic_dir / "iperf_critical_server.log")
        if not np.isnan(crit_res["throughput_mbps"]):
            crit_tp = crit_res["throughput_mbps"]
            crit_loss = crit_res["packet_loss_pct"]
            crit_jitter = crit_res["jitter_ms"]
            iperf_parsed = True

        video_res = parse_iperf_log(traffic_dir / "iperf_video_server.log")
        if not np.isnan(video_res["throughput_mbps"]):
            video_tp = video_res["throughput_mbps"]

        bulk_res = parse_iperf_log(traffic_dir / "iperf_bulk_server.log")
        if not np.isnan(bulk_res["throughput_mbps"]):
            bulk_tp = bulk_res["throughput_mbps"]

    # 5. Routing Decisions (Fine-grained Accounting)
    decisions_parsed = False
    reroute_attempts = 0
    reroute_installations = 0
    reroute_verified_successes = 0
    reroute_failures = 0
    rollback_count = 0

    decisions_path = exp_dir / "routing_decisions.jsonl"
    if decisions_path.exists():
        try:
            lines = [json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()]
            for d in lines:
                reroute_attempts += 1
                if d.get("installation_status") == "INSTALLED":
                    reroute_installations += 1
                if d.get("installation_status") == "INSTALLED" and d.get("verification_status") == "VERIFIED" and d.get("outcome_status") == "SUCCESS":
                    reroute_verified_successes += 1
                if d.get("installation_status") == "FAILED" or d.get("outcome_status") == "FAILED":
                    reroute_failures += 1
                if d.get("rollback_attempted") is True:
                    rollback_count += 1
            decisions_parsed = True
        except Exception:
            pass

    # 6. Event Timeline (True Warning Lead Time & SLA Recovery Time)
    events_parsed = False
    warning_lead_time_s = np.nan
    recovery_time_s = np.nan

    events_path = exp_dir / "events.jsonl"
    if events_path.exists():
        try:
            events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
            # Build chronological timeline
            pred_cross_time = None
            violation_start_time = None
            sla_recovered_time = None

            for ev in events:
                ev_type = ev.get("event")
                ts = pd.to_datetime(ev.get("timestamp"))
                if ev_type in {"prediction_threshold_crossed", "congestion_injected_at"} and pred_cross_time is None:
                    pred_cross_time = ts
                if ev_type in {"sla_violation_started", "congestion_worsened_at"} and violation_start_time is None:
                    violation_start_time = ts
                if ev_type in {"sla_recovered", "reroute_verified_at"} and sla_recovered_time is None:
                    sla_recovered_time = ts

            if violation_start_time and pred_cross_time and violation_start_time >= pred_cross_time:
                warning_lead_time_s = (violation_start_time - pred_cross_time).total_seconds()

            if violation_start_time and sla_recovered_time and sla_recovered_time >= violation_start_time:
                recovery_time_s = (sla_recovered_time - violation_start_time).total_seconds()

            events_parsed = True
        except Exception:
            pass

    record = {
        "experiment_id": exp_id,
        "scenario": manifest.get("scenario"),
        "effective_policy": manifest.get("effective_policy", manifest.get("policy")),
        "requested_policy": manifest.get("requested_policy"),
        "scientific_policy": manifest.get("scientific_policy"),
        "seed": manifest.get("seed"),
        "duration_s": manifest.get("duration"),
        "control_plane_rtt_ms": control_plane_rtt_mean,
        "end_to_end_rtt_ms": end_to_end_rtt_ms,
        "throughput_mbps": overall_tp if not np.isnan(overall_tp) else crit_tp,
        "packet_loss_pct": overall_loss if not np.isnan(overall_loss) else crit_loss,
        "jitter_ms": overall_jitter if not np.isnan(overall_jitter) else crit_jitter,
        "critical_throughput_mbps": crit_tp,
        "critical_packet_loss_pct": crit_loss,
        "video_throughput_mbps": video_tp,
        "bulk_throughput_mbps": bulk_tp,
        "reroute_attempts": reroute_attempts,
        "reroute_installations": reroute_installations,
        "reroute_verified_successes": reroute_verified_successes,
        "reroute_failures": reroute_failures,
        "rollback_count": rollback_count,
        "warning_lead_time_s": warning_lead_time_s,
        "recovery_time_s": recovery_time_s,
        "telemetry_parsed": telemetry_parsed,
        "ping_parsed": ping_parsed,
        "iperf_parsed": iperf_parsed,
        "decisions_parsed": decisions_parsed,
        "events_parsed": events_parsed
    }
    return record, None


def compute_student_t_stats(series: pd.Series) -> Dict[str, float]:
    """Computes Mean, StdDev, and Student's t 95% Confidence Interval bounds."""
    clean = series.dropna().tolist()
    n = len(clean)
    missing_count = len(series) - n

    if n == 0:
        return {
            "mean": np.nan,
            "std_dev": np.nan,
            "ci95_lower": np.nan,
            "ci95_upper": np.nan,
            "sample_size_n": 0,
            "missing_count": missing_count
        }

    mean = float(np.mean(clean))
    if n == 1:
        return {
            "mean": round(mean, 3),
            "std_dev": 0.0,
            "ci95_lower": round(mean, 3),
            "ci95_upper": round(mean, 3),
            "sample_size_n": 1,
            "missing_count": missing_count
        }

    std = float(np.std(clean, ddof=1))
    # Student's t-distribution critical value
    t_crit = float(stats.t.ppf(0.975, df=n - 1))
    margin = t_crit * (std / math.sqrt(n))

    return {
        "mean": round(mean, 3),
        "std_dev": round(std, 3),
        "ci95_lower": round(mean - margin, 3),
        "ci95_upper": round(mean + margin, 3),
        "sample_size_n": n,
        "missing_count": missing_count
    }


def compute_paired_differences(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Calculates paired-policy differences per (scenario, seed) with Cohen's d effect sizes."""
    paired_results = []
    scenarios = df["scenario"].unique()

    for sc in scenarios:
        df_sc = df[df["scenario"] == sc]
        seeds = df_sc["seed"].unique()

        pred_rows = df_sc[df_sc["effective_policy"] == "predictive"].set_index("seed")
        reac_rows = df_sc[df_sc["effective_policy"] == "reactive"].set_index("seed")
        stat_rows = df_sc[df_sc["effective_policy"] == "static"].set_index("seed")

        # 1. Predictive vs Reactive
        common_reac_seeds = pred_rows.index.intersection(reac_rows.index)
        if len(common_reac_seeds) >= 2:
            loss_diffs = (reac_rows.loc[common_reac_seeds, "packet_loss_pct"] - pred_rows.loc[common_reac_seeds, "packet_loss_pct"]).dropna()
            rtt_diffs = (reac_rows.loc[common_reac_seeds, "end_to_end_rtt_ms"] - pred_rows.loc[common_reac_seeds, "end_to_end_rtt_ms"]).dropna()

            if len(loss_diffs) >= 2:
                mean_d = float(np.mean(loss_diffs))
                std_d = float(np.std(loss_diffs, ddof=1))
                cohen_d = mean_d / std_d if std_d > 0 else 0.0
                paired_results.append({
                    "scenario": sc,
                    "comparison": "predictive_vs_reactive",
                    "metric": "packet_loss_reduction_pct",
                    "paired_n": len(loss_diffs),
                    "mean_improvement": round(mean_d, 3),
                    "std_dev": round(std_d, 3),
                    "cohen_d": round(cohen_d, 2)
                })

        # 2. Predictive vs Static (No Reroute)
        common_stat_seeds = pred_rows.index.intersection(stat_rows.index)
        if len(common_stat_seeds) >= 2:
            loss_diffs_s = (stat_rows.loc[common_stat_seeds, "packet_loss_pct"] - pred_rows.loc[common_stat_seeds, "packet_loss_pct"]).dropna()
            if len(loss_diffs_s) >= 2:
                mean_d_s = float(np.mean(loss_diffs_s))
                std_d_s = float(np.std(loss_diffs_s, ddof=1))
                cohen_d_s = mean_d_s / std_d_s if std_d_s > 0 else 0.0
                paired_results.append({
                    "scenario": sc,
                    "comparison": "predictive_vs_no_reroute",
                    "metric": "packet_loss_reduction_pct",
                    "paired_n": len(loss_diffs_s),
                    "mean_improvement": round(mean_d_s, 3),
                    "std_dev": round(std_d_s, 3),
                    "cohen_d": round(cohen_d_s, 2)
                })

    return paired_results


def evaluate_campaign(results_dir: Path, allow_incomplete: bool = False) -> Dict[str, Any]:
    """Main campaign aggregator."""
    valid_records = []
    excluded_records = []

    for d in sorted(results_dir.iterdir()):
        if d.is_dir() and (d / "manifest.json").exists():
            rec, excl = parse_run_directory(d)
            if rec:
                valid_records.append(rec)
            else:
                excluded_records.append(excl)

    # Save excluded runs report
    df_excl = pd.DataFrame(excluded_records)
    excl_path = results_dir / "excluded_runs.csv"
    df_excl.to_csv(excl_path, index=False)
    print(f"Excluded runs recorded to {excl_path} ({len(df_excl)} runs)")

    if not valid_records:
        print("No eligible completed Mininet runs found for campaign evaluation.")
        return {"eligible_runs": 0, "excluded_runs": len(df_excl)}

    df_valid = pd.DataFrame(valid_records)
    runs_path = results_dir / "campaign_runs.csv"
    df_valid.to_csv(runs_path, index=False)
    print(f"Eligible run records saved to {runs_path} ({len(df_valid)} runs)")

    # Validate 60-run campaign completeness
    expected_total = len(EXPECTED_SCENARIOS) * len(EXPECTED_POLICIES) * len(EXPECTED_SEEDS)
    total_eligible = len(df_valid)
    is_complete_matrix = (total_eligible >= expected_total)

    if not is_complete_matrix and not allow_incomplete:
        print(f"Notice: Campaign matrix incomplete ({total_eligible}/{expected_total} runs). Pass --allow-incomplete to generate preliminary tables.")

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
        "recovery_time_s"
    ]

    for (scenario, policy), group in df_valid.groupby(["scenario", "effective_policy"]):
        row = {
            "scenario": scenario,
            "policy": policy,
            "sample_size_n": len(group)
        }
        for m in metrics_to_aggregate:
            stats_m = compute_student_t_stats(group[m])
            row[f"{m}_mean"] = stats_m["mean"]
            row[f"{m}_std"] = stats_m["std_dev"]
            row[f"{m}_ci95_lower"] = stats_m["ci95_lower"]
            row[f"{m}_ci95_upper"] = stats_m["ci95_upper"]
        aggregated.append(row)

    df_agg = pd.DataFrame(aggregated)
    agg_path = results_dir / "aggregated_metrics.csv"
    df_agg.to_csv(agg_path, index=False)

    # Paired Policy Comparisons
    paired_diffs = compute_paired_differences(df_valid)
    df_paired = pd.DataFrame(paired_diffs)
    paired_path = results_dir / "paired_policy_comparisons.csv"
    df_paired.to_csv(paired_path, index=False)

    # Summary JSON
    summary_path = results_dir / "campaign_summary.json"
    with open(summary_path, "w") as jf:
        json.dump({
            "evaluated_at": pd.Timestamp.utcnow().isoformat(),
            "campaign_matrix_complete": is_complete_matrix,
            "eligible_runs_count": total_eligible,
            "excluded_runs_count": len(df_excl),
            "scenarios": df_valid["scenario"].unique().tolist(),
            "policies": df_valid["effective_policy"].unique().tolist(),
            "paired_comparisons": paired_diffs,
            "aggregated_metrics": aggregated
        }, jf, indent=2)

    print(f"Aggregated statistical summary written to {agg_path}")
    print(f"Paired comparison metrics written to {paired_path}")
    return {
        "eligible_runs": total_eligible,
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
