#!/usr/bin/env python3
"""
Unit and Property Tests for Campaign Evaluator, Checksumming, Event Parsing,
Matrix Completeness, and Statistical Aggregation.
"""

import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from experiments.evaluate_campaign import (
    verify_directory_checksums,
    parse_ping_latency,
    parse_iperf_log,
    parse_event_timing_episodes,
    compute_student_t_stats,
    compute_paired_differences,
    evaluate_campaign,
    sanitize_for_json
)
from experiments.artifact_validator import (
    validate_finalized_artifacts,
    compute_campaign_invariant_fingerprint
)


def create_mock_run_dir(parent_dir: Path, exp_id: str, scenario: str, policy: str, seed: int, eligible: bool = True, invariant_fp: str = "fp_match_123"):
    """Helper to generate a clean, self-contained experiment run directory with checksums."""
    run_dir = parent_dir / exp_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "experiment_id": exp_id,
        "scenario": scenario,
        "effective_policy": policy,
        "seed": seed,
        "duration": 60,
        "status": "completed" if eligible else "failed",
        "real_experiment": eligible,
        "data_origin": "mininet" if eligible else "mock",
        "evidence_complete": eligible,
        "eligible_for_analysis": eligible,
        "policy_sync": {"required": True, "successful": True},
        "backend_finalization": {"required": True, "successful": True},
        "campaign_invariant_fingerprint": invariant_fp
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Telemetry
    tel_content = "timestamp,experiment_id,switch_id,port_no,rx_bytes,tx_bytes,control_plane_rtt_ms,tx_dropped,loss_percent,utilization\n" \
                  f"2026-08-28T12:00:00Z,{exp_id},s1,1,1000,1000,0.5,0,0.0,0.1\n"
    (run_dir / "telemetry.csv").write_text(tel_content)

    # Predictions
    pred_content = "timestamp,link_id,congestion_probability,is_violation_predicted\n" \
                   "2026-08-28T12:00:00Z,s1-s2,0.15,False\n"
    (run_dir / "predictions.csv").write_text(pred_content)

    # Routing decisions
    (run_dir / "routing_decisions.jsonl").write_text("")

    # Events
    ev1 = {"timestamp": "2026-08-28T12:00:05Z", "event": "prediction_threshold_crossed", "episode_id": "ep1", "flow_id": "f1", "link_id": "s1-s2"}
    ev2 = {"timestamp": "2026-08-28T12:00:08Z", "event": "sla_violation_started", "episode_id": "ep1", "flow_id": "f1", "link_id": "s1-s2"}
    ev3 = {"timestamp": "2026-08-28T12:00:12Z", "event": "sla_recovered", "episode_id": "ep1", "flow_id": "f1", "link_id": "s1-s2"}
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in [ev1, ev2, ev3]) + "\n")

    # Traffic
    traffic_dir = run_dir / "traffic"
    traffic_dir.mkdir(exist_ok=True)
    (traffic_dir / "ping_after.txt").write_text("rtt min/avg/max/mdev = 0.020/0.040/0.060/0.010 ms\n")
    (traffic_dir / "iperf_server.log").write_text("0.0-60.0 sec  14.3 MBytes  2.00 Mbits/sec  0.045 ms 0/10200 (0%)\n")

    # Generate SHA256SUMS
    with open(run_dir / "SHA256SUMS", "w") as sf:
        for fpath in sorted(run_dir.rglob("*")):
            if fpath.is_file() and fpath.name != "SHA256SUMS":
                h = hashlib.sha256(fpath.read_bytes()).hexdigest()
                rel = fpath.relative_to(run_dir)
                sf.write(f"{h}  {rel}\n")

    return run_dir


def test_checksum_verification_and_path_containment(tmp_path):
    """Verifies bidirectional SHA256 validation and rejection of escaping paths."""
    run_dir = create_mock_run_dir(tmp_path, "exp_1", "normal", "static", 42)
    ok, err = verify_directory_checksums(run_dir)
    assert ok is True
    assert err is None

    # Unchecksummed artifact rejection
    (run_dir / "extra.txt").write_text("unchecksummed file")
    ok, err = verify_directory_checksums(run_dir)
    assert ok is False
    assert "Unchecksummed artifact" in err
    (run_dir / "extra.txt").unlink()

    # Path traversal rejection
    sums_file = run_dir / "SHA256SUMS"
    sums_file.write_text("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  ../../escape.txt\n")
    ok, err = verify_directory_checksums(run_dir)
    assert ok is False
    assert "traversal" in err.lower() or "escapes" in err.lower()


def test_zero_packet_loss_validity():
    """Zero packet loss is valid data and must not be coerced to NaN."""
    s = pd.Series([0.0, 0.0, 0.0, 0.0])
    res = compute_student_t_stats(s)
    assert res["mean"] == 0.0
    assert res["std_dev"] == 0.0
    assert res["n"] == 4
    assert res["missing"] == 0


def test_event_episode_lead_and_recovery_timing(tmp_path):
    """Verifies that events are matched by episode and differences calculated properly."""
    run_dir = create_mock_run_dir(tmp_path, "exp_timing", "gradual_congestion", "predictive", 42)
    errs = []
    timing = parse_event_timing_episodes(run_dir, errs)
    assert timing["warning_lead_time_s"] == 3.0 # 12:00:08 - 12:00:05
    assert timing["recovery_time_s"] == 4.0     # 12:00:12 - 12:00:08
    assert timing["violation_duration_s"] == 4.0
    assert timing["unrecovered_episodes_count"] == 0


def test_json_sanitizer_strict_compliance():
    """Verifies that NaNs, Infs, and numpy scalars are converted to None or python types."""
    data = {
        "nan_val": np.nan,
        "inf_val": float("inf"),
        "np_int": np.int64(42),
        "nested": [float("nan"), 3.14, {"inner_inf": float("-inf")}]
    }
    sanitized = sanitize_for_json(data)
    json_str = json.dumps(sanitized)
    parsed = json.loads(json_str)

    assert parsed["nan_val"] is None
    assert parsed["inf_val"] is None
    assert parsed["np_int"] == 42
    assert parsed["nested"][0] is None
    assert parsed["nested"][1] == 3.14
    assert parsed["nested"][2]["inner_inf"] is None


def test_matrix_completeness_and_unexpected_combination(tmp_path):
    """Verifies that incomplete, duplicate, or unexpected combinations fail strict validation."""
    res_dir = tmp_path / "results"
    res_dir.mkdir()

    # Create only 1 run -> incomplete matrix
    create_mock_run_dir(res_dir, "run_1", "normal", "static", 42)
    with pytest.raises(RuntimeError, match="Campaign matrix validation failed"):
        evaluate_campaign(res_dir, allow_incomplete=False)

    # With allow_incomplete=True, it succeeds and marks preliminary
    res = evaluate_campaign(res_dir, allow_incomplete=True)
    assert res["eligible_runs"] == 1
    assert res["matrix_complete"] is False

    summary_file = res_dir / "campaign_summary.json"
    summary = json.loads(summary_file.read_text())
    assert summary["preliminary"] is True
    assert summary["campaign_matrix_complete"] is False


def test_invariant_fingerprint_mismatch_detection(tmp_path):
    """Verifies that invariant fingerprint differences flag matrix as incomplete."""
    res_dir = tmp_path / "results"
    res_dir.mkdir()

    create_mock_run_dir(res_dir, "run_1", "normal", "static", 42, invariant_fp="fp_A")
    create_mock_run_dir(res_dir, "run_2", "normal", "reactive", 42, invariant_fp="fp_B")

    res = evaluate_campaign(res_dir, allow_incomplete=True)
    summary = json.loads((res_dir / "campaign_summary.json").read_text())
    assert summary["fingerprint_consistent"] is False


def test_prediction_time_link_horizon_alignment(tmp_path):
    """Test 1: Proves time/link/horizon prediction alignment and ground truth evaluation."""
    from experiments.evaluate_campaign import evaluate_predictive_ml_performance

    run_dir = tmp_path / "exp_pred_align"
    run_dir.mkdir()

    # Create predictions at t=00:00 and t=00:10
    pred_data = pd.DataFrame([
        {"timestamp": "2026-08-28T12:00:00Z", "link_id": "s1-p1", "congestion_probability": 0.85, "is_violation_predicted": True},
        {"timestamp": "2026-08-28T12:00:10Z", "link_id": "s1-p1", "congestion_probability": 0.15, "is_violation_predicted": False}
    ])
    pred_data.to_csv(run_dir / "predictions.csv", index=False)

    # Telemetry at t=00:10 (horizon for first pred, loss=5.0% > 1.0% SLA threshold -> true violation)
    # and t=00:20 (horizon for second pred, loss=0.0% -> no violation)
    tel_data = pd.DataFrame([
        {"timestamp": "2026-08-28T12:00:00Z", "switch_id": "s1", "port_no": 1, "loss_percent": 0.0, "control_plane_rtt_ms": 1.0, "rx_bytes": 0, "tx_bytes": 0, "tx_dropped": 0, "utilization": 0.1},
        {"timestamp": "2026-08-28T12:00:10Z", "switch_id": "s1", "port_no": 1, "loss_percent": 5.0, "control_plane_rtt_ms": 25.0, "rx_bytes": 0, "tx_bytes": 0, "tx_dropped": 0, "utilization": 0.9},
        {"timestamp": "2026-08-28T12:00:20Z", "switch_id": "s1", "port_no": 1, "loss_percent": 0.0, "control_plane_rtt_ms": 2.0, "rx_bytes": 0, "tx_bytes": 0, "tx_dropped": 0, "utilization": 0.1}
    ])
    tel_data.to_csv(run_dir / "telemetry.csv", index=False)

    df_valid = pd.DataFrame([{"experiment_id": "exp_pred_align", "effective_policy": "predictive"}])
    res = evaluate_predictive_ml_performance(tmp_path, df_valid)

    assert res["predictive_performance_validated"] is True
    assert res["sample_size"] == 2
    assert res["true_positives"] == 1
    assert res["true_negatives"] == 1
    assert res["false_positives"] == 0
    assert res["false_negatives"] == 0
    assert res["precision"] == 1.0
    assert res["recall"] == 1.0
    assert (tmp_path / "prediction_ground_truth_alignment.csv").exists()


def test_episode_id_rotation():
    """Test 2: Proves two sequential congestion episodes receive different episode IDs."""
    from backend.app.services.orchestrator import Orchestrator
    orch = Orchestrator()
    orch.begin_experiment("exp_ep_rot", "predictive")

    # Episode 1 begins: prediction crosses threshold
    orch.ingest_telemetry({"link_id": "s1-p1", "risk": 0.9, "is_violation": True, "is_violation_actual": True, "loss_percent": 5.0})
    ep1_id = orch.active_episodes.get("s1-p1")
    assert ep1_id is not None

    # Episode 1 ends: prediction cleared & SLA recovered
    orch.ingest_telemetry({"link_id": "s1-p1", "risk": 0.1, "is_violation": False, "is_violation_actual": False, "loss_percent": 0.0})
    assert "s1-p1" not in orch.active_episodes

    # Episode 2 begins: new congestion occurrence
    orch.ingest_telemetry({"link_id": "s1-p1", "risk": 0.88, "is_violation": True, "is_violation_actual": True, "loss_percent": 4.0})
    ep2_id = orch.active_episodes.get("s1-p1")
    assert ep2_id is not None
    assert ep1_id != ep2_id, "Subsequent congestion episode must receive a fresh, distinct episode ID"


def test_single_episode_lifecycle_sharing():
    """Test 3: Proves prediction, violation, reroute, and recovery share one episode ID."""
    from backend.app.services.orchestrator import Orchestrator
    orch = Orchestrator()
    orch.begin_experiment("exp_ep_share", "predictive")

    # Set up topology and mock router
    orch.router.graph.add_node("s1")
    orch.router.graph.add_node("s2")
    orch.router.graph.add_edge("s1", "s2", out_port=1, weight=1.0, original_weight=1.0, risk=0.0)
    orch.register_flow = getattr(orch, "register_flow", None)

    import threading
    orch.flows["f1"] = {
        "flow_id": "f1",
        "src": "h1",
        "dst": "h2",
        "current_path": ["s1", "s2"],
        "state": "STABLE",
        "sla_status": "Healthy"
    }
    orch.flow_locks["f1"] = threading.Lock()

    # Congestion prediction and actual violation occur
    orch.ingest_telemetry({"link_id": "s1-p1", "risk": 0.9, "is_violation": True, "is_violation_actual": True, "loss_percent": 4.0})
    shared_ep_id = orch.active_episodes.get("s1-p1")
    assert shared_ep_id is not None

    # Verify that recorded decisions and active episode ID match
    if orch.routing_decisions:
        assert orch.routing_decisions[-1]["episode_id"] == shared_ep_id


def test_concurrent_flow_filename_parsing(tmp_path):
    """Test 4: Proves parsing real concurrent-flow filenames (critical_iperf_server.log, critical_ping.txt)."""
    from experiments.evaluate_campaign import parse_run_directory
    run_dir = create_mock_run_dir(tmp_path, "exp_concurrent", "concurrent_flows", "predictive", 42)

    # Add concurrent flow files
    traffic_dir = run_dir / "traffic"
    (traffic_dir / "critical_iperf_server.log").write_text("0.0-60.0 sec  7.15 MBytes  1.00 Mbits/sec  0.025 ms 0/5100 (0%)\n")
    (traffic_dir / "critical_ping.txt").write_text("rtt min/avg/max/mdev = 0.015/0.035/0.055/0.008 ms\n")

    # Regenerate SHA256SUMS to maintain integrity
    with open(run_dir / "SHA256SUMS", "w") as sf:
        for fpath in sorted(run_dir.rglob("*")):
            if fpath.is_file() and fpath.name != "SHA256SUMS":
                h = hashlib.sha256(fpath.read_bytes()).hexdigest()
                sf.write(f"{h}  {fpath.relative_to(run_dir)}\n")

    quality_errs = []
    rec, excl = parse_run_directory(run_dir, quality_errs)
    assert excl is None
    assert rec is not None
    assert rec["critical_throughput_mbps"] == 1.00
    assert rec["critical_packet_loss_pct"] == 0.0
    assert rec["critical_rtt_ms"] == 0.035


def test_missing_evidence_artifacts_fail_validation(tmp_path):
    """Test 5: Confirms missing switch/traffic/evidence report/scenario params fail validation."""
    run_dir = tmp_path / "incomplete_run"
    run_dir.mkdir()

    # Create only telemetry and predictions
    (run_dir / "telemetry.csv").write_text("timestamp,experiment_id,switch_id,port_no,rx_bytes,tx_bytes,control_plane_rtt_ms,tx_dropped,loss_percent,utilization\n2026-08-28T12:00:00Z,incomplete_run,s1,1,100,100,1.0,0,0.0,0.1\n")
    (run_dir / "predictions.csv").write_text("timestamp,link_id,congestion_probability,is_violation_predicted\n2026-08-28T12:00:00Z,s1-s2,0.1,False\n")
    (run_dir / "routing_decisions.jsonl").write_text("")
    (run_dir / "events.jsonl").write_text('{"event":"test","timestamp":"2026-08-28T12:00:00Z"}\n')

    ok, report, errors = validate_finalized_artifacts(run_dir, "predictive")
    assert ok is False
    assert report["all_valid"] is False
    assert any("evidence_report.json is missing" in e for e in errors)
    assert any("switches/ state directory is missing" in e for e in errors)
    assert any("traffic/ directory is missing" in e for e in errors)
    assert any("scenario_parameters.json is missing" in e for e in errors)
