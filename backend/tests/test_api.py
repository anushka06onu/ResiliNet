import os
import sys

from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.main import app

client = TestClient(app)

def test_telemetry_ingest_and_features():
    for i in range(15):
        payload = {
            "switch_id": "s1",
            "port_no": 1,
            "features": {
                "rx_bytes": 1000.0 * (i + 1),
                "tx_bytes": 5000.0 * (i + 1),
                "control_plane_rtt_ms": 15.0,
                "tx_dropped": 0.0,
                "loss_percent": 0.1,
                "utilization": 0.5
            }
        }
        response = client.post("/api/v1/telemetry/ingest", json=payload)
        assert response.status_code == 200

def test_predict_endpoint():
    payload = {
        "switch_id": "s1",
        "port_no": 1,
        "features": {
            "loss_mean_30s": 0.1,
            "tx_dropped_max": 0,
            "control_plane_rtt_ms": 10.0,
            "rx_bytes_slope": 50.0,
            "tx_bytes_rate": 500.0
        }
    }
    response = client.post("/api/v1/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "congestion_probability" in data
    assert "is_violation_predicted" in data

def test_topology_ingest():
    payload = {
        "nodes": [{"id": "s1", "type": "switch"}, {"id": "s2", "type": "switch"}],
        "links": [{"source": "s1", "source_port": 1, "target": "s2", "target_port": 2, "capacity": "10Mbps"}]
    }
    response = client.post("/api/v1/topology/ingest", json=payload)
    assert response.status_code == 200
    
    # Verify it was stored
    response = client.get("/api/v1/topology/current")
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["id"] == "s1"

def test_routing_decisions_query():
    response = client.get("/api/v1/routing/decisions?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)

def test_health_endpoints():
    live_res = client.get("/health/live")
    assert live_res.status_code == 200
    assert live_res.json()["status"] == "ok"

    ready_res = client.get("/health/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "ready"
    assert ready_res.json()["components"]["database_connected"] is True

def test_paginated_endpoints():
    # Experiments pagination
    exp_res = client.get("/api/v1/experiments?limit=5&offset=0")
    assert exp_res.status_code == 200
    exp_data = exp_res.json()
    assert "items" in exp_data
    assert "total" in exp_data
    assert isinstance(exp_data["items"], list)

    # Telemetry history pagination
    tel_res = client.get("/api/v1/telemetry/history?port_no=1&limit=10&offset=0")
    assert tel_res.status_code == 200
    tel_data = tel_res.json()
    assert "items" in tel_data
    assert "total" in tel_data
    assert isinstance(tel_data["items"], list)

    # Predictions history pagination
    pred_res = client.get("/api/v1/predictions/history?port_no=1&limit=10&offset=0")
    assert pred_res.status_code == 200
    pred_data = pred_res.json()
    assert "items" in pred_data
    assert "total" in pred_data
    assert isinstance(pred_data["items"], list)

def test_experiments_scenarios_endpoint():
    res = client.get("/api/v1/experiments/scenarios")
    assert res.status_code == 200
    scenarios = res.json()
    assert "concurrent_flows" in scenarios
    assert "normal" in scenarios


def test_internal_configure_and_finalize_endpoints(tmp_path):
    # Test internal configure endpoint
    res_cfg = client.post("/api/v1/internal/experiments/test_api_exp/configure", json={"policy": "reactive_threshold"})
    assert res_cfg.status_code == 200
    data_cfg = res_cfg.json()
    assert data_cfg["effective_policy"] == "reactive"
    assert data_cfg["status"] == "CONFIGURED"

    # Test invalid policy rejection
    res_invalid = client.post("/api/v1/internal/experiments/test_api_exp/configure", json={"policy": "invalid_policy_name"})
    assert res_invalid.status_code == 422

    # Test internal finalize endpoint
    res_fin = client.post("/api/v1/internal/experiments/test_api_exp/finalize")
    assert res_fin.status_code == 200
    assert res_fin.json()["status"] == "FINALIZED"


def test_isolated_experiment_manifest_discovery_and_detail(tmp_path):
    from pathlib import Path
    import json

    project_root = Path(__file__).resolve().parents[2]
    res_dir = project_root / "experiments" / "results" / "test_api_isolated_run"
    res_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "experiment_id": "test_api_isolated_run",
        "scenario": "gradual_congestion",
        "seed": 42,
        "status": "completed",
        "requested_policy": "predictive_ml",
        "effective_policy": "predictive"
    }
    with open(res_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)

    try:
        # Listing endpoint must discover the isolated experiment
        res_list = client.get("/api/v1/experiments")
        assert res_list.status_code == 200
        items = res_list.json()["items"]
        found = any(item.get("id") == "test_api_isolated_run" for item in items)
        assert found, "Isolated experiment manifest not found in /api/v1/experiments"

        # Detail endpoint must return status
        res_detail = client.get("/api/v1/experiments/test_api_isolated_run")
        assert res_detail.status_code == 200
        assert res_detail.json()["status"] == "completed"
    finally:
        import shutil
        if res_dir.exists():
            shutil.rmtree(res_dir)
