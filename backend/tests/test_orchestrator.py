import os
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.app.services.orchestrator import Orchestrator


def test_orchestrator_initial_state():
    orchestrator = Orchestrator()
    assert orchestrator.flows == {}

def test_orchestrator_safe_evaluation():
    orchestrator = Orchestrator()
    
    # Mock routing success
    orchestrator.router.evaluate_and_reroute = MagicMock(return_value=(True, "Success", ["s1", "s2", "s3"]))
    
    # Add a mock flow
    flow_id = "f_1"
    import threading
    orchestrator.flows[flow_id] = {
        "flow_id": flow_id,
        "src": "h1",
        "dst": "h2",
        "tier": "Critical",
        "state": "STABLE",
        "sla_status": "Healthy",
        "current_path": ["s1", "s2"]
    }
    orchestrator.flow_locks[flow_id] = threading.Lock()
    
    # Mock graph edge
    orchestrator.router.graph.add_node("s1")
    orchestrator.router.graph.add_node("s2")
    orchestrator.router.graph.add_edge("s1", "s2", out_port=1, risk=0.0)
    
    event = {
        "payload": {
            "link_id": "s1-p1",
            "predicted_risk": 0.9,
            "is_violation_predicted": True
        }
    }
    
    # Trigger handle telemetry event manually to bypass threading for synchronous test
    # (In the real orchestrator handle_telemetry_event spins off threads, so we can mock or just wait)
    orchestrator.handle_telemetry_event(event)
    
    import time
    time.sleep(0.5) # Wait for thread to finish
    
    # Flow should be stable after successful rerouting in our simple mockup
    assert orchestrator.flows[flow_id]["state"] == "STABLE"
