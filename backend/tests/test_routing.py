import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# We must add network to the path since we run pytest from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from network.routing.predictive_routing import PredictiveRouter

@pytest.fixture
def router():
    # Force min_risk_improvement=-1 to guarantee it attempts installation
    r = PredictiveRouter(topology_json='non_existent.json', min_risk_improvement=-1.0)
    
    # Build a simple mock topology
    # s1 -> s2 (port 1), s2 -> s1 (port 2)
    # s2 -> s3 (port 3), s3 -> s2 (port 4)
    r.graph.add_node("s1", type="switch")
    r.graph.add_node("s2", type="switch")
    r.graph.add_node("s3", type="switch")
    
    r.graph.add_edge("s1", "s2", weight=1, original_weight=1, risk=0, out_port=1)
    r.graph.add_edge("s2", "s1", weight=1, original_weight=1, risk=0, out_port=2)
    
    r.graph.add_edge("s2", "s3", weight=1, original_weight=1, risk=0, out_port=3)
    r.graph.add_edge("s3", "s2", weight=1, original_weight=1, risk=0, out_port=4)
    
    return r

@patch('network.routing.predictive_routing.subprocess.run')
def test_evaluate_and_reroute_success(mock_run, router):
    # Setup mock to always return success
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_run.return_value = mock_res
    
    # Reroute from s1 to s3
    current_path = ["s1", "s2"] # dummy
    success, msg = router.evaluate_and_reroute(
        flow_id="flow_1", source="s1", target="s3", 
        current_path=current_path, nw_src="10.0.0.1", nw_dst="10.0.0.2"
    )
    
    assert success
    assert msg == "Reroute installed successfully"
    
    # Verify subprocess.run calls
    # Should install forward path: s1 -> s2, s2 -> s3
    # Should install reverse path: s3 -> s2, s2 -> s1
    assert mock_run.call_count == 4
    
    calls = mock_run.call_args_list
    forward_1 = " ".join(calls[0][0][0])
    forward_2 = " ".join(calls[1][0][0])
    reverse_1 = " ".join(calls[2][0][0])
    reverse_2 = " ".join(calls[3][0][0])
    
    # Verify forward commands
    assert "add-flow" in forward_1 and "s1" in forward_1
    assert "nw_src=10.0.0.1" in forward_1 and "nw_dst=10.0.0.2" in forward_1
    assert "output:1" in forward_1 # s1 -> s2 is port 1
    
    assert "add-flow" in forward_2 and "s2" in forward_2
    assert "nw_src=10.0.0.1" in forward_2 and "nw_dst=10.0.0.2" in forward_2
    assert "output:3" in forward_2 # s2 -> s3 is port 3
    
    # Verify reverse commands (nw_src and nw_dst swapped)
    assert "add-flow" in reverse_1 and "s3" in reverse_1
    assert "nw_src=10.0.0.2" in reverse_1 and "nw_dst=10.0.0.1" in reverse_1
    assert "output:4" in reverse_1 # s3 -> s2 is port 4
    
    assert "add-flow" in reverse_2 and "s2" in reverse_2
    assert "nw_src=10.0.0.2" in reverse_2 and "nw_dst=10.0.0.1" in reverse_2
    assert "output:2" in reverse_2 # s2 -> s1 is port 2


@patch('network.routing.predictive_routing.subprocess.run')
def test_evaluate_and_reroute_failure_and_rollback(mock_run, router):
    # Setup mock to fail on the 3rd call (reverse path first step)
    def side_effect(cmd, **kwargs):
        mock_res = MagicMock()
        if "s3" in cmd and "add-flow" in cmd:
            mock_res.returncode = 1
            mock_res.stderr = b"Flow table full"
        else:
            mock_res.returncode = 0
        return mock_res
        
    mock_run.side_effect = side_effect
    
    current_path = ["s1", "s2"]
    success, msg = router.evaluate_and_reroute(
        flow_id="flow_2", source="s1", target="s3", 
        current_path=current_path, nw_src="10.0.0.1", nw_dst="10.0.0.2"
    )
    
    assert not success
    assert "failed" in msg.lower()
    
    # Verify rollback
    # 2 successful forward adds, 1 failed reverse add -> 3 add-flow calls
    # Should trigger del-flows for the 2 successful adds
    calls = mock_run.call_args_list
    assert len(calls) == 5
    
    # 0, 1 = forward add
    # 2 = reverse add (failed)
    # 3, 4 = rollbacks
    
    rollback_1 = " ".join(calls[3][0][0])
    rollback_2 = " ".join(calls[4][0][0])
    
    assert "del-flows" in rollback_1 and "s1" in rollback_1
    assert "nw_src=10.0.0.1" in rollback_1 and "nw_dst=10.0.0.2" in rollback_1
    
    assert "del-flows" in rollback_2 and "s2" in rollback_2
    assert "nw_src=10.0.0.1" in rollback_2 and "nw_dst=10.0.0.2" in rollback_2
