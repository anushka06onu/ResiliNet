#!/usr/bin/env python3
"""
ResiliNet Empirical Campaign Evaluation & Metrics Aggregator.
Parses isolated experiment directories, computes statistical metrics across policies,
and generates structured comparative analysis tables (Mean, StdDev, 95% Confidence Intervals).
"""

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
import pandas as pd


def parse_ping_latency(ping_file: Path) -> Dict[str, float]:
    """Parses min/avg/max/mdev from ping output text."""
    if not ping_file.exists():
        return {}
    content = ping_file.read_text()
    # match rtt min/avg/max/mdev = 0.024/0.045/0.065/0.015 ms
    match = re.search(r"rtt min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms", content)
    if match:
        return {
            "rtt_min_ms": float(match.group(1)),
            "rtt_avg_ms": float(match.group(2)),
            "rtt_max_ms": float(match.group(3)),
            "rtt_mdev_ms": float(match.group(4))
        }
    return {}


def parse_iperf_metrics(client_log: Path, server_log: Path) -> Dict[str, float]:
    """Parses bandwidth, jitter, and loss percentage from iperf text logs."""
    metrics = {"throughput_mbps": 0.0, "jitter_ms": 0.0, "packet_loss_pct": 0.0}
    if server_log.exists():
        content = server_log.read_text()
        # match: 0.0-60.0 sec  14.3 MBytes  2.00 Mbits/sec  0.045 ms 0/10200 (0%)
        match = re.findall(r"([\d\.]+)\s+Mbits/sec\s+([\d\.]+)\s+ms\s+\d+/\d+\s+\(([\d\.]+)%\)", content)
        if match:
            last = match[-1]
            metrics["throughput_mbps"] = float(last[0])
            metrics["jitter_ms"] = float(last[1])
            metrics["packet_loss_pct"] = float(last[2])
            return metrics

    if client_log.exists():
        content = client_log.read_text()
        match = re.findall(r"([\d\.]+)\s+Mbits/sec", content)
        if match:
            metrics["throughput_mbps"] = float(match[-1])

    return metrics


def parse_experiment_directory(exp_dir: Path) -> Dict[str, Any]:
    """Extracts all metrics, provenance records, and event milestones from a single run directory."""
    manifest_path = exp_dir / "manifest.json"
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception:
        return None

    record = {
        "experiment_id": manifest.get("experiment_id", exp_dir.name),
        "scenario": manifest.get("scenario", "unknown"),
        "seed": manifest.get("seed", 0),
        "requested_policy": manifest.get("requested_policy", "unknown"),
        "effective_policy": manifest.get("effective_policy", manifest.get("policy", "unknown")),
        "scientific_policy": manifest.get("scientific_policy", "unknown"),
        "status": manifest.get("status", "unknown"),
        "real_experiment": manifest.get("real_experiment", False),
        "data_origin": manifest.get("data_origin", "unknown"),
        "duration_s": manifest.get("duration", 0),
        "reroute_count": 0,
        "avg_loss_pct": 0.0,
        "avg_rtt_ms": 0.0,
        "throughput_mbps": 0.0,
        "warning_lead_time_s": None,
        "recovery_time_s": None
    }

    # 1. Routing Decisions
    decisions_path = exp_dir / "routing_decisions.jsonl"
    if decisions_path.exists():
        decisions = [json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()]
        record["reroute_count"] = sum(1 for d in decisions if d.get("outcome_status") == "SUCCESS" or d.get("installation_status") == "INSTALLED")

    # 2. Telemetry statistics
    telemetry_path = exp_dir / "telemetry.csv"
    if telemetry_path.exists():
        try:
            df_tel = pd.read_csv(telemetry_path)
            if "loss_percent" in df_tel.columns and not df_tel.empty:
                record["avg_loss_pct"] = float(df_tel["loss_percent"].mean())
            if "control_plane_rtt_ms" in df_tel.columns and not df_tel.empty:
                record["avg_rtt_ms"] = float(df_tel["control_plane_rtt_ms"].mean())
        except Exception:
            pass

    # 3. Traffic statistics
    traffic_dir = exp_dir / "traffic"
    if traffic_dir.exists():
        ping_res = parse_ping_latency(traffic_dir / "ping_after.txt")
        if "rtt_avg_ms" in ping_res:
            record["avg_rtt_ms"] = ping_res["rtt_avg_ms"]

        iperf_res = parse_iperf_metrics(traffic_dir / "iperf_client.log", traffic_dir / "iperf_server.log")
        if iperf_res.get("throughput_mbps"):
            record["throughput_mbps"] = iperf_res["throughput_mbps"]
        if iperf_res.get("packet_loss_pct"):
            record["avg_loss_pct"] = iperf_res["packet_loss_pct"]

    # 4. Events timeline analysis
    events_path = exp_dir / "events.jsonl"
    if events_path.exists():
        try:
            events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
            event_times = {e["event"]: pd.to_datetime(e["timestamp"]) for e in events if "event" in e and "timestamp" in e}
            
            # Warning lead time: if prediction or reroute occurred before congestion injection
            if "congestion_injected_at" in event_times and "reroute_started_at" in event_times:
                lead = (event_times["congestion_injected_at"] - event_times["reroute_started_at"]).total_seconds()
                record["warning_lead_time_s"] = lead

            # Recovery time: from congestion injection until measurement finished or reroute verified
            if "congestion_injected_at" in event_times and "measurement_finished_at" in event_times:
                rec_t = (event_times["measurement_finished_at"] - event_times["congestion_injected_at"]).total_seconds()
                record["recovery_time_s"] = rec_t
        except Exception:
            pass

    return record


def compute_confidence_interval(data: List[float], confidence: float = 0.95) -> tuple[float, float, float]:
    """Returns (mean, std_dev, margin_of_error)."""
    clean = [x for x in data if x is not None and not math.isnan(x)]
    if not clean:
        return 0.0, 0.0, 0.0
    n = len(clean)
    mean = float(np.mean(clean))
    if n < 2:
        return mean, 0.0, 0.0
    std = float(np.std(clean, ddof=1))
    # z critical value for 95% is ~1.96, or t-distribution approximation
    z = 1.96
    margin = z * (std / math.sqrt(n))
    return mean, std, margin


def evaluate_campaign(results_dir: Path) -> Dict[str, Any]:
    """Scans all isolated result runs, aggregates statistical summaries, and outputs reports."""
    records = []
    for d in sorted(results_dir.iterdir()):
        if d.is_dir() and (d / "manifest.json").exists():
            parsed = parse_experiment_directory(d)
            if parsed:
                records.append(parsed)

    if not records:
        print("No experiment results found to evaluate.")
        return {}

    df = pd.DataFrame(records)
    runs_summary_path = results_dir / "campaign_runs.csv"
    df.to_csv(runs_summary_path, index=False)
    print(f"Saved raw campaign run records to {runs_summary_path} ({len(df)} runs)")

    # Aggregate by (scenario, effective_policy)
    aggregated = []
    groups = df.groupby(["scenario", "effective_policy"])

    for (scenario, policy), group in groups:
        loss_mean, loss_std, loss_ci = compute_confidence_interval(group["avg_loss_pct"].tolist())
        rtt_mean, rtt_std, rtt_ci = compute_confidence_interval(group["avg_rtt_ms"].tolist())
        tp_mean, tp_std, tp_ci = compute_confidence_interval(group["throughput_mbps"].tolist())
        reroute_mean, reroute_std, reroute_ci = compute_confidence_interval(group["reroute_count"].tolist())
        lead_mean, lead_std, lead_ci = compute_confidence_interval(group["warning_lead_time_s"].dropna().tolist())

        aggregated.append({
            "scenario": scenario,
            "policy": policy,
            "sample_size_n": len(group),
            "throughput_mbps_mean": round(tp_mean, 2),
            "throughput_mbps_ci95": round(tp_ci, 2),
            "packet_loss_pct_mean": round(loss_mean, 2),
            "packet_loss_pct_ci95": round(loss_ci, 2),
            "rtt_ms_mean": round(rtt_mean, 2),
            "rtt_ms_ci95": round(rtt_ci, 2),
            "reroute_count_mean": round(reroute_mean, 2),
            "warning_lead_time_s_mean": round(lead_mean, 2) if lead_mean else 0.0
        })

    df_agg = pd.DataFrame(aggregated)
    agg_summary_path = results_dir / "aggregated_metrics.csv"
    df_agg.to_csv(agg_summary_path, index=False)

    summary_json_path = results_dir / "campaign_summary.json"
    with open(summary_json_path, "w") as jf:
        json.dump({
            "evaluated_at": pd.Timestamp.utcnow().isoformat(),
            "total_runs": len(df),
            "scenarios": df["scenario"].unique().tolist(),
            "policies": df["effective_policy"].unique().tolist(),
            "aggregated_metrics": aggregated
        }, jf, indent=2)

    print(f"Aggregated comparative evaluation report saved to {agg_summary_path}")
    print(df_agg.to_string(index=False))
    return {"total_runs": len(df), "aggregated": aggregated}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate ResiliNet Campaign Results")
    parser.add_argument("--results-dir", type=str, default="experiments/results", help="Path to experiments results directory")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    res_path = Path(args.results_dir) if Path(args.results_dir).is_absolute() else project_root / args.results_dir
    res_path.mkdir(parents=True, exist_ok=True)
    evaluate_campaign(res_path)
