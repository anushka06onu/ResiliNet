import numpy as np
import pandas as pd
import pytest
from data_pipeline.validate_dataset import validate_raw_telemetry, validate_feature_dataset


def test_validate_telemetry_dataframe_clean():
    clean_df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01 12:00:00", periods=20, freq="2s"),
        "experiment_id": ["exp_1"] * 20,
        "switch_id": ["s1"] * 20,
        "port_no": [1] * 20,
        "rx_bytes": [1000 * (i + 1) for i in range(20)],
        "tx_bytes": [5000 * (i + 1) for i in range(20)],
        "control_plane_rtt_ms": [12.5 + i * 0.1 for i in range(20)],
        "tx_dropped": [0] * 20,
        "loss_percent": [0.1] * 20,
        "utilization": [0.45] * 20,
    })

    is_valid, violations = validate_raw_telemetry(clean_df)
    assert is_valid is True
    assert len(violations) == 0


def test_validate_telemetry_dataframe_detects_violations():
    corrupted_df = pd.DataFrame({
        # Out-of-order timestamp
        "timestamp": [
            "2026-01-01 12:00:10",
            "2026-01-01 12:00:05", # inversion
            "2026-01-01 12:00:20"
        ],
        "experiment_id": ["exp_corrupt"] * 3,
        "rx_bytes": [100, 200, 300],
        "tx_bytes": [100, 200, 300],
        # Negative drops
        "tx_dropped": [-5, 0, 1],
        # Out of bounds loss
        "loss_percent": [150.0, 0.0, 0.0],
        # Negative RTT
        "control_plane_rtt_ms": [-10.0, 15.0, 20.0],
    })

    is_valid, violations = validate_raw_telemetry(corrupted_df)
    assert is_valid is False
    assert any("Timestamps are not strictly non-decreasing" in v for v in violations)
    assert any("Negative tx_dropped" in v for v in violations)
    assert any("Loss percent out of bounds" in v for v in violations)
    assert any("Implausible RTT" in v for v in violations)


def test_validate_feature_dataset_clean_and_corrupt():
    clean_feature_df = pd.DataFrame({
        "experiment_id": ["exp_1"] * 10,
        "loss_mean_30s": [0.1] * 10,
        "tx_dropped_max": [0] * 10,
        "control_plane_rtt_ms": [10.0] * 10,
        "rx_bytes_slope": [50.0] * 10,
        "tx_bytes_rate": [500.0] * 10,
        "sla_violated_in_horizon": [0] * 8 + [1] * 2,
    })
    is_valid, violations = validate_feature_dataset(clean_feature_df)
    assert is_valid is True
    assert len(violations) == 0

    # Test missing feature
    missing_col_df = pd.DataFrame({
        "experiment_id": ["exp_1"] * 3,
        "loss_mean_30s": [0.1, 0.2, 0.3],
        "tx_dropped_max": [0, 0, 0],
        "control_plane_rtt_ms": [10.0, 12.0, 15.0],
        "rx_bytes_slope": [50.0, 60.0, 70.0],
        "sla_violated_in_horizon": [0, 1, 0],
    })
    is_valid, violations = validate_feature_dataset(missing_col_df)
    assert is_valid is False
    assert any("Missing required model feature: tx_bytes_rate" in v for v in violations)

    # Test corrupted with NaN / Inf and non-binary class
    corrupt_feature_df = pd.DataFrame({
        "experiment_id": ["exp_1"] * 3,
        "loss_mean_30s": [0.1, np.inf, 0.2],
        "tx_dropped_max": [0, 0, 0],
        "control_plane_rtt_ms": [10.0, 12.0, np.nan],
        "rx_bytes_slope": [50.0, 60.0, 70.0],
        "tx_bytes_rate": [500.0, 600.0, 700.0],
        "sla_violated_in_horizon": [0, 1, 2], # invalid class 2
    })
    is_valid, violations = validate_feature_dataset(corrupt_feature_df)
    assert is_valid is False
    assert any("contains infinite values" in v for v in violations)
    assert any("contains 1 NaN values" in v for v in violations)
    assert any("invalid non-binary classes" in v for v in violations)


def test_validate_telemetry_dataframe_sample_real_run():
    """Validate that the checked-in sample_real_run telemetry adheres to physical constraints."""
    from pathlib import Path
    telemetry_path = Path(__file__).resolve().parents[2] / "experiments" / "sample_real_run" / "telemetry.csv"
    if telemetry_path.exists():
        df = pd.read_csv(telemetry_path)
        is_valid, violations = validate_raw_telemetry(df)
        assert is_valid is True, f"Sample real run failed validation: {violations}"


def test_sample_real_run_manifest_provenance():
    """Verify artifact relationships, checksums, and provenance recorded in sample_real_run."""
    import hashlib
    import json
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    sample_dir = project_root / "experiments" / "sample_real_run"
    manifest_path = sample_dir / "manifest.json"
    sums_path = sample_dir / "SHA256SUMS"
    meta_path = project_root / "ml" / "artifacts" / "model_metadata.json"
    model_path = project_root / "ml" / "artifacts" / "lightgbm_model.txt"
    scenario_path = project_root / "experiments" / "scenarios" / "gradual_congestion.py"
    topology_path = project_root / "network" / "topologies" / "campus_health.py"

    assert manifest_path.exists(), "Sample real run manifest.json must be present"
    assert sums_path.exists(), "Sample real run SHA256SUMS must be present"

    def sha256(p):
        h = hashlib.sha256()
        with open(p, "rb") as fl:
            for chunk in iter(lambda: fl.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    # 1. Verify every artifact in SHA256SUMS exists, is non-empty, and has matching digest
    with open(sums_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            expected_hash, fname = line.split(maxsplit=1)
            target = sample_dir / fname.strip()
            assert target.exists(), f"Artifact {fname} from SHA256SUMS missing"
            assert target.stat().st_size > 0, f"Artifact {fname} is unexpectedly empty"
            assert sha256(target) == expected_hash, f"Hash mismatch for {fname}"

    # 2. Verify manifest metadata
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    with open(meta_path, "r") as f:
        meta = json.load(f)

    hashes = manifest.get("artifact_hashes", {})
    assert hashes.get("model_run_id") == meta.get("run_id")
    assert hashes.get("model_file_sha256") == sha256(model_path)
    assert hashes.get("scenario_file_sha256") == sha256(scenario_path)
    assert hashes.get("topology_file_sha256") == sha256(topology_path)

    # 3. Verify scientific evidence boundaries and environment
    assert manifest.get("mode") == "FIXTURE"
    assert manifest.get("evidence_scope") == "parser_and_interface_testing"
    assert manifest.get("data_origin") == "constructed_fixture"
    assert manifest.get("real_experiment") is False
    assert manifest.get("predictive_performance_validated") is False
    assert manifest.get("status") == "completed"

    env = manifest.get("environment", {})
    assert len(env.get("git_commit", "")) >= 7
    assert env.get("mininet_version") is not None
    assert env.get("ryu_version") is not None

    procs = manifest.get("process_results", {})
    for proc_name, exit_code in procs.items():
        assert exit_code == 0, f"Process {proc_name} returned non-zero exit code {exit_code}"


def test_mock_experiment_execution_and_provenance(tmp_path):
    """Verify mock experiment execution produces isolated artifacts and transparent metadata in tmp_path."""
    import json
    from pathlib import Path
    from experiments.run_experiment import run_experiment

    exp_id = "test_mock_provenance_run"
    run_experiment(
        scenario="normal",
        duration=1,
        seed=42,
        experiment_id=exp_id,
        policy="predictive",
        allow_mock=True,
        results_root=tmp_path
    )

    res_dir = tmp_path / exp_id
    manifest_path = res_dir / "manifest.json"
    sums_path = res_dir / "SHA256SUMS"

    assert manifest_path.exists()
    assert sums_path.exists()
    assert (res_dir / "telemetry.csv").exists()
    assert (res_dir / "predictions.csv").exists()
    assert (res_dir / "routing_decisions.jsonl").exists()
    assert (res_dir / "controller.log").exists()
    assert (res_dir / "scenario.log").exists()

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    assert manifest["mode"] == "MOCK_TEST"
    assert manifest["status"] == "fixture_generated"
    assert manifest["real_experiment"] is False
    assert manifest["data_origin"] == "mock"
    assert manifest["evidence_scope"] == "pipeline_testing"
    assert manifest["predictive_performance_validated"] is False
    assert manifest["requested_policy"] == "predictive"
    assert manifest["effective_policy"] == "predictive"
    assert manifest["policy_implementation"] == "PredictiveRouter:predictive"


def test_scenario_results_dir_isolation(tmp_path):
    """Verify that evidence capture writes strictly to the isolated run directory."""
    from experiments.evidence_collector import capture_switch_state

    run_dir = tmp_path / "test_run_isolation"
    run_dir.mkdir(parents=True)

    # Capture switch state in isolated run_dir
    res = capture_switch_state(["s1", "s2"], run_dir, stage="before")

    assert (run_dir / "evidence_report.json").exists()
    assert (run_dir / "switches").exists()
    assert not (tmp_path / "evidence_report.json").exists()
