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
                "control_plane_rtt_ms": 15.0,
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

def test_predictive_routing_module():
    import sys
    import os
    # We must add network to the path since we run pytest from backend
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
    from network.routing.predictive_routing import PredictiveRouter
    
    router = PredictiveRouter(topology_json='non_existent.json', min_risk_improvement=-1.0) # Empty graph
    
    # Evaluate unreachable
    success, msg = router.evaluate_and_reroute(flow_id="f1", source="s1", target="s2", current_path=["s1", "s2"], nw_src="10.0.0.1", nw_dst="10.0.0.2")
    assert not success
    assert "unreachable" in msg or "identical" in msg

    # Manually add topology to test rollback / failure
    router.graph.add_node("s1", type="switch")
    router.graph.add_node("s2", type="switch")
    router.graph.add_edge("s1", "s2", weight=1, original_weight=1, risk=0, out_port=1)
    # Target to source is missing an out_port explicitly
    router.graph.add_edge("s2", "s1", weight=1, original_weight=1, risk=0, out_port=None)
    
    success, msg = router.evaluate_and_reroute(flow_id="f2", source="s1", target="s2", current_path=["s1", "s3", "s2"], nw_src="10.0.0.1", nw_dst="10.0.0.2")
    
    assert not success
    assert "failed" in msg.lower()
