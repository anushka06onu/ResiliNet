import os
import sys
from unittest.mock import MagicMock, patch

import pytest

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
    import hashlib
    cookie = int(hashlib.md5(b"flow_1").hexdigest()[:8], 16)
    cookie_hex = hex(cookie)
    
    def side_effect(cmd, **kwargs):
        mock_res = MagicMock()
        mock_res.returncode = 0
        if "dump-flows" in cmd:
            # We output all possible variations so it passes verification for any node
            mock_res.stdout = f"cookie={cookie_hex}, priority=100, nw_src=10.0.0.1, nw_dst=10.0.0.2, actions=output:1 \n \
                                cookie={cookie_hex}, priority=100, nw_src=10.0.0.1, nw_dst=10.0.0.2, actions=output:3 \n \
                                cookie={cookie_hex}, priority=100, nw_src=10.0.0.2, nw_dst=10.0.0.1, actions=output:4 \n \
                                cookie={cookie_hex}, priority=100, nw_src=10.0.0.2, nw_dst=10.0.0.1, actions=output:2".encode()
        return mock_res
    mock_run.side_effect = side_effect
    
    # Reroute from s1 to s3
    current_path = ["s1", "s2"] # dummy
    result = router.evaluate_and_reroute(
        flow_id="flow_1", source="s1", target="s3", 
        current_path=current_path, nw_src="10.0.0.1", nw_dst="10.0.0.2"
    )
    
    assert result.success
    assert result.message == "Reroute installed successfully"
    
    # Verify subprocess.run calls
    # Should install forward path: s1 -> s2, s2 -> s3
    # Should install reverse path: s3 -> s2, s2 -> s1
    # Plus 4 dump-flows calls for verification
    # Plus 4 dump-flows calls for traffic verification
    assert mock_run.call_count == 12
    
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
    result = router.evaluate_and_reroute(
        flow_id="flow_2", source="s1", target="s3", 
        current_path=current_path, nw_src="10.0.0.1", nw_dst="10.0.0.2"
    )
    
    assert not result.success
    assert "failed" in result.message.lower()
    
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
    
    import hashlib
    cookie = int(hashlib.md5(b"flow_2").hexdigest()[:8], 16)
    
    assert "del-flows" in rollback_1 and "s1" in rollback_1
    assert f"cookie={cookie}/-1" in rollback_1
    
    assert "del-flows" in rollback_2 and "s2" in rollback_2
    assert f"cookie={cookie}/-1" in rollback_2


@patch('network.routing.predictive_routing.subprocess.run')
def test_evaluate_and_reroute_verification_failure_and_rollback(mock_run, router):
    # Setup mock to succeed on all add-flows but fail on the dump-flows verification for s2
    def side_effect(cmd, **kwargs):
        mock_res = MagicMock()
        mock_res.returncode = 0
        if "dump-flows" in cmd:
            if "s2" in cmd:
                # Missing output action to trigger failure
                mock_res.stdout = b"cookie=0x1234, priority=100, nw_src=10.0.0.1, nw_dst=10.0.0.2"
            else:
                import hashlib
                cookie = int(hashlib.md5(b"flow_3").hexdigest()[:8], 16)
                cookie_hex = hex(cookie)
                mock_res.stdout = f"cookie={cookie_hex}, priority=100, nw_src=10.0.0.1, nw_dst=10.0.0.2, actions=output:1 \n \
                                    cookie={cookie_hex}, priority=100, nw_src=10.0.0.2, nw_dst=10.0.0.1, actions=output:4".encode()
        return mock_res
        
    mock_run.side_effect = side_effect
    
    current_path = ["s1", "s2"]
    result = router.evaluate_and_reroute(
        flow_id="flow_3", source="s1", target="s3", 
        current_path=current_path, nw_src="10.0.0.1", nw_dst="10.0.0.2"
    )
    
    assert not result.success
    assert "failed" in result.message.lower()
    
    # 4 successful adds + dump-flows until s2 fails.
    # At rollback, it should issue 4 del-flows commands
    # So we should see del-flows being called.
    calls = mock_run.call_args_list
    rollbacks = [c for c in calls if "del-flows" in c[0][0]]
    assert len(rollbacks) == 4

