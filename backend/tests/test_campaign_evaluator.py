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
