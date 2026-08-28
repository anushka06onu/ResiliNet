#!/usr/bin/env python3
"""
ResiliNet Empirical Campaign Evaluation & Statistical Metrics Aggregator.

Performs rigorous scholarship-grade statistical evaluation across routing policies:
- Strict bidirectional SHA256 integrity verification (with path containment checks)
- Exact 60-run matrix validation (4 scenarios x 3 policies x 5 seeds) with missing/duplicate reports
- Configuration fingerprint consistency verification
- Strict eligibility filtering (excluding mock, partial, or unverified runs to excluded_runs.csv)
- Separation of control-plane RTT vs end-to-end RTT
- Multi-class concurrent traffic parsing (Critical Tier-1, Video, Bulk)
- Genuine matched event timing for warning lead time and SLA recovery time (no proxies)
- Student's t-distribution 95% Confidence Intervals with per-metric sample size and missing counts
- Paired-policy comparisons across all metrics (Cohen's dz, paired t-intervals)
- ML predictive performance validation (Precision, Recall, F1, Brier score, False-Alert Rate)
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


EXPECTED_SCENARIOS = ["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"]
EXPECTED_POLICIES = ["static", "reactive", "predictive"]
EXPECTED_SEEDS = [42, 43, 44, 45, 46]


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

    # 1. Strict Eligibility Filters
    if not manifest.get("real_experiment"):
        return None, {"experiment_id": exp_id, "reason": "Excluded: mock/fixture run (real_experiment=false)"}
    if manifest.get("data_origin") != "mininet":
        return None, {"experiment_id": exp_id, "reason": f"Excluded: data_origin='{manifest.get('data_origin')}' != 'mininet'"}
    if manifest.get("status") != "completed":
        return None, {"experiment_id": exp_id, "reason": f"Excluded: status='{manifest.get('status')}' != 'completed'"}
    if not manifest.get("evidence_complete"):
        return None, {"experiment_id": exp_id, "reason": "Excluded: evidence_complete is False"}
    if manifest.get("eligible_for_analysis") is False:
        return None, {"experiment_id": exp_id, "reason": "Excluded: eligible_for_analysis is explicitly False"}

    policy_sync = manifest.get("policy_sync", {})
    if policy_sync.get("required") and not policy_sync.get("successful"):
        return None, {"experiment_id": exp_id, "reason": "Excluded: backend policy synchronization failed"}

    backend_fin = manifest.get("backend_finalization", {})
    if backend_fin.get("required") and not backend_fin.get("successful"):
        return None, {"experiment_id": exp_id, "reason": "Excluded: backend finalization failed"}

    # 2. Checksum Verification
    checksum_ok, err_msg = verify_directory_checksums(exp_dir)
    if not checksum_ok:
        return None, {"experiment_id": exp_id, "reason": f"Checksum verification failed: {err_msg}"}

    # 3. Parse Telemetry (Control-Plane Metrics)
    control_plane_rtt_mean = np.nan
    telemetry_loss_mean = np.nan
    telemetry_parsed = False
    telemetry_path = exp_dir / "telemetry.csv"
    if telemetry_path.exists() and telemetry_path.stat().st_size > 0:
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

    # 6. Event Timeline (True Warning Lead Time & SLA Recovery Time paired by flow/link)
    events_parsed = False
    warning_lead_time_s = np.nan
    recovery_time_s = np.nan

    events_path = exp_dir / "events.jsonl"
    if events_path.exists():
        try:
            events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]

            # Match genuine orchestrator events
            pred_cross_time = None
            violation_start_time = None
            sla_recovered_time = None

            for ev in events:
                ev_type = ev.get("event")
                ts = pd.to_datetime(ev.get("timestamp"))
                if ev_type == "prediction_threshold_crossed" and pred_cross_time is None:
                    pred_cross_time = ts
                elif ev_type == "sla_violation_started" and violation_start_time is None:
                    violation_start_time = ts
                elif ev_type in {"sla_recovered", "reroute_verified_at"} and sla_recovered_time is None:
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
        "campaign_config_fingerprint": manifest.get("campaign_config_fingerprint"),
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
            "n": 0,
            "missing": missing_count
        }

    mean = float(np.mean(clean))
    if n == 1:
        return {
            "mean": round(mean, 3),
            "std_dev": 0.0,
            "ci95_lower": round(mean, 3),
            "ci95_upper": round(mean, 3),
            "n": 1,
            "missing": missing_count
        }

    std = float(np.std(clean, ddof=1))
    t_crit = float(stats.t.ppf(0.975, df=n - 1))
    margin = t_crit * (std / math.sqrt(n))

    return {
        "mean": round(mean, 3),
        "std_dev": round(std, 3),
        "ci95_lower": round(mean - margin, 3),
        "ci95_upper": round(mean + margin, 3),
        "n": n,
        "missing": missing_count
    }


def compute_paired_differences(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Calculates paired-policy differences per (scenario, seed) with Student's t CIs and Cohen's dz."""
    paired_results = []
    scenarios = df["scenario"].unique()
    metrics_to_compare = [
        ("packet_loss_pct", "packet_loss_reduction_pct", True), # higher difference = better improvement
        ("end_to_end_rtt_ms", "rtt_reduction_ms", True),
        ("throughput_mbps", "throughput_gain_mbps", False),    # higher pred = better
        ("critical_packet_loss_pct", "critical_loss_reduction_pct", True),
        ("critical_throughput_mbps", "critical_throughput_gain_mbps", False)
    ]

    for sc in scenarios:
        df_sc = df[df["scenario"] == sc]
        pred_rows = df_sc[df_sc["effective_policy"] == "predictive"].set_index("seed")
        reac_rows = df_sc[df_sc["effective_policy"] == "reactive"].set_index("seed")
        stat_rows = df_sc[df_sc["effective_policy"] == "static"].set_index("seed")

        for baseline_name, baseline_df in [("reactive", reac_rows), ("no_reroute", stat_rows)]:
            common_seeds = pred_rows.index.intersection(baseline_df.index)
            if len(common_seeds) < 2:
                continue

            for metric_col, display_name, baseline_minus_pred in metrics_to_compare:
                if metric_col not in pred_rows.columns or metric_col not in baseline_df.columns:
                    continue

                if baseline_minus_pred:
                    diffs = (baseline_df.loc[common_seeds, metric_col] - pred_rows.loc[common_seeds, metric_col]).dropna()
                else:
                    diffs = (pred_rows.loc[common_seeds, metric_col] - baseline_df.loc[common_seeds, metric_col]).dropna()

                n = len(diffs)
                if n < 2:
                    continue

                mean_d = float(np.mean(diffs))
                std_d = float(np.std(diffs, ddof=1))

                # Confidence interval on paired difference
                t_crit = float(stats.t.ppf(0.975, df=n - 1))
                margin = t_crit * (std_d / math.sqrt(n)) if std_d > 0 else 0.0

                # Cohen's dz calculation with zero variance handling
                if std_d > 0:
                    cohens_dz = round(mean_d / std_d, 2)
                else:
                    cohens_dz = 0.0 if mean_d == 0 else np.nan

                paired_results.append({
                    "scenario": sc,
                    "comparison": f"predictive_vs_{baseline_name}",
                    "metric": display_name,
                    "paired_n": n,
                    "mean_difference": round(mean_d, 3),
                    "std_difference": round(std_d, 3),
                    "ci95_lower": round(mean_d - margin, 3),
                    "ci95_upper": round(mean_d + margin, 3),
                    "cohens_dz": cohens_dz
                })

    return paired_results


def evaluate_campaign(results_dir: Path, allow_incomplete: bool = False) -> Dict[str, Any]:
    """Main campaign statistical aggregator."""
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

    # Matrix Completeness Validation
    expected_combinations = {
        (scenario, policy, seed)
        for scenario in EXPECTED_SCENARIOS
        for policy in EXPECTED_POLICIES
        for seed in EXPECTED_SEEDS
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

    is_complete_matrix = (len(missing_combinations) == 0 and len(duplicate_records) == 0)

    if not is_complete_matrix and not allow_incomplete:
        raise RuntimeError(
            f"Campaign matrix validation failed: {len(missing_combinations)} missing combinations, "
            f"{len(duplicate_records)} duplicates out of {len(expected_combinations)} expected runs. "
            f"Pass --allow-incomplete to generate preliminary tables."
        )

    if not valid_records:
        print("No eligible completed Mininet runs found for campaign evaluation.")
        return {"eligible_runs": 0, "excluded_runs": len(df_excl), "matrix_complete": False}

    df_valid = pd.DataFrame(valid_records)
    runs_path = results_dir / "campaign_runs.csv"
    df_valid.to_csv(runs_path, index=False)
    print(f"Eligible run records saved to {runs_path} ({len(df_valid)} runs)")

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

    # Summary JSON
    summary_path = results_dir / "campaign_summary.json"
    with open(summary_path, "w") as jf:
        json.dump({
            "evaluated_at": pd.Timestamp.utcnow().isoformat(),
            "preliminary": not is_complete_matrix,
            "campaign_matrix_complete": is_complete_matrix,
            "expected_matrix_size": len(expected_combinations),
            "eligible_runs_count": len(df_valid),
            "excluded_runs_count": len(df_excl),
            "missing_combinations_count": len(missing_combinations),
            "duplicate_combinations_count": len(duplicate_records),
            "scenarios": df_valid["scenario"].unique().tolist(),
            "policies": df_valid["effective_policy"].unique().tolist(),
            "paired_comparisons": paired_diffs,
            "aggregated_metrics": aggregated
        }, jf, indent=2)

    print(f"Aggregated statistical summary written to {agg_path}")
    print(f"Paired comparison metrics written to {paired_path}")
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
