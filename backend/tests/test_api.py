import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_telemetry_ingest_and_features():
    # Insert multiple telemetry payloads to trigger rolling 30s calculation
    for i in range(15):
        payload = {
            "switch_id": "s1",
            "port_no": "1",
            "features": {
                "utilization": 0.5,
                "loss_mean_30s": 0.1,
                "tx_dropped_max": 2,
                "latency_mean_30s": 15.0,
                "rx_bytes_slope": 1000.0,
                "tx_bytes_rate": 5000.0
            }
        }
        response = client.post("/api/v1/telemetry/ingest", json=payload)
        assert response.status_code == 200

def test_predict_endpoint():
    payload = {
        "switch_id": "s1",
        "port_no": "1",
        "features": {
            "loss_mean_30s": 0.1,
            "tx_dropped_max": 0,
            "latency_mean_30s": 10.0,
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
        "nodes": [{"id": "s1", "type": "switch"}],
        "links": [{"source": "s1", "source_port": "1", "target": "s2", "target_port": "2"}]
    }
    response = client.post("/api/v1/topology/ingest", json=payload)
    assert response.status_code == 200
    
    # Verify it was stored
    response = client.get("/api/v1/topology/current")
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "s1"
