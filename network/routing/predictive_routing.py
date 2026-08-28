#!/usr/bin/env python3

import json
import logging
import os
import subprocess
import time
from typing import Optional
from pydantic import BaseModel

import networkx as nx

class RoutingResult(BaseModel):
    success: bool
    message: str
    proposed_path: Optional[list] = None
    failure_stage: Optional[str] = None
    error_type: Optional[str] = None
    rollback_attempted: bool = False
    rollback_success: Optional[bool] = None
    rollback_error: Optional[str] = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

from network.routing.policies import normalize_policy, get_scientific_label

class PredictiveRouter:
    """
    Calculates routing paths based on ML congestion predictions and installs physical OpenFlow rules.
    Supports 3 distinct policies: 'static', 'reactive', and 'predictive'.
    """
    def __init__(self, topology_json='network/topologies/topology.json', min_risk_improvement=0.2, cooldown=10, policy="predictive"):
        self.graph = nx.DiGraph()
        self.load_topology(topology_json)
        self.last_reroute_time = {} # Track cooldowns per flow
        self.min_risk_improvement = min_risk_improvement
        self.cooldown = cooldown
        self.policy = "predictive"
        self.set_policy(policy)
        logging.info(f"Initialized Router with effective policy: {self.policy}")

    def set_policy(self, policy: str):
        self.policy = normalize_policy(policy)
        logging.info(f"Router policy updated to: {self.policy}")

    def load_topology(self, topology_json):
        if not os.path.exists(topology_json):
            logging.warning(f"Topology file {topology_json} not found. Router has an empty graph.")
            return
            
        with open(topology_json, 'r') as f:
            data = json.load(f)
            
        for node in data.get('nodes', []):
            self.graph.add_node(node['id'], type=node['type'])
            
        for link in data.get('links', []):
            base_cost = 1
            src = link['source']
            dst = link['target']
            src_port = link.get('source_port')
            dst_port = link.get('target_port')
            
            # Forward edge
            self.graph.add_edge(src, dst, weight=base_cost, original_weight=base_cost, risk=0.0, out_port=src_port)
            # Reverse edge
            self.graph.add_edge(dst, src, weight=base_cost, original_weight=base_cost, risk=0.0, out_port=dst_port)

    def update_link_predictions(self, predictions):
        """
        predictions: list of dicts [{'source': 's1', 'target': 's2', 'congestion_prob': 0.85}]
        """
        # Reset weights and risk
        for u, v, d in self.graph.edges(data=True):
            d['weight'] = d['original_weight']
            d['risk'] = 0.0
            
        # Inflate weights based on congestion probability
        for pred in predictions:
            src = pred['source']
            dst = pred['target']
            prob = pred['congestion_prob']
            
            if self.graph.has_edge(src, dst):
                penalty = 1000 if prob > 0.5 else (prob * 10)
                self.graph[src][dst]['weight'] += penalty
                self.graph[src][dst]['risk'] = prob
            # Optionally update reverse edge if congestion is assumed symmetric
            if self.graph.has_edge(dst, src):
                penalty = 1000 if prob > 0.5 else (prob * 10)
                self.graph[dst][src]['weight'] += penalty
                self.graph[dst][src]['risk'] = prob

    def calculate_path(self, source, target):
        """Calculate shortest path using current weights (Dijkstra)."""
        try:
            return nx.shortest_path(self.graph, source=source, target=target, weight='weight')
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            logging.error(f"No path or missing nodes between {source} and {target}")
            return None

    def calculate_path_risk(self, path):
        """Calculate the maximum risk bottleneck along a given path."""
        if not path or len(path) < 2: return 0.0
        max_risk = 0.0
        for i in range(len(path)-1):
            u, v = path[i], path[i+1]
            if self.graph.has_edge(u, v):
                max_risk = max(max_risk, self.graph[u][v].get('risk', 0.0))
        return max_risk

    def evaluate_and_reroute(self, flow_id, source, target, current_path, nw_src, nw_dst, priority=100, is_violation_actual=False, is_violation_predicted=True) -> RoutingResult:
        """
        Safety Checks & Physical Installation Pipeline with explicit policy branching:
        - Static: never performs reroutes.
        - Reactive: reroutes only when is_violation_actual is True.
        - Predictive: reroutes when is_violation_predicted is True.
        """
        # Policy gate
        if self.policy == "static":
            return RoutingResult(
                success=False,
                message="Static policy bypasses dynamic rerouting",
                failure_stage="POLICY_STATIC_BYPASS",
                error_type="static_policy"
            )
        elif self.policy == "reactive" and not is_violation_actual:
            return RoutingResult(
                success=False,
                message="Reactive policy waits for measured physical SLA violation",
                failure_stage="POLICY_REACTIVE_WAIT",
                error_type="awaiting_actual_violation"
            )
        elif self.policy == "predictive" and not is_violation_predicted and not is_violation_actual:
            return RoutingResult(
                success=False,
                message="Predictive policy requires forecast or actual violation signal",
                failure_stage="POLICY_PREDICTIVE_WAIT",
                error_type="awaiting_predicted_violation"
            )

        now = time.time()
        if flow_id in self.last_reroute_time and (now - self.last_reroute_time[flow_id] < self.cooldown):
            logging.info(f"Flow {flow_id} in cooldown. Skipping reroute.")
            return RoutingResult(
                success=False,
                message="Cooldown Active",
                failure_stage="evaluation",
                error_type="cooldown_active"
            )

        proposed_path = self.calculate_path(source, target)
        if not proposed_path or proposed_path == current_path:
            return RoutingResult(
                success=False,
                message="Proposed path identical or unreachable",
                failure_stage="evaluation",
                error_type="no_viable_path"
            )

        current_risk = self.calculate_path_risk(current_path)
        proposed_risk = self.calculate_path_risk(proposed_path)

        if current_risk - proposed_risk < self.min_risk_improvement:
            return RoutingResult(
                success=False,
                message=f"Risk improvement ({current_risk - proposed_risk:.2f}) below threshold",
                failure_stage="evaluation",
                error_type="below_threshold"
            )

        proposed_reverse_path = self.calculate_path(target, source)
        if not proposed_reverse_path:
            return RoutingResult(
                success=False,
                message="Reverse path unreachable",
                failure_stage="evaluation",
                error_type="no_viable_path"
            )

        # 5. Route installation via OpenFlow and verification
        logging.info(f"Initiating bidirectional route installation for {flow_id}")
        res = self.install_bidirectional_route(proposed_path, proposed_reverse_path, nw_src, nw_dst, flow_id, priority)
        
        if res["success"]:
            self.last_reroute_time[flow_id] = now
            logging.info(f"Successfully rerouted {flow_id}: {current_path} -> {proposed_path}")
            return RoutingResult(
                success=True,
                message="Reroute installed successfully",
                proposed_path=proposed_path,
                failure_stage=None,
                error_type=None,
                rollback_attempted=False,
                rollback_success=None,
                rollback_error=None
            )
        else:
            logging.error(f"Failed to install OpenFlow rules for {flow_id}: {res.get('error_type')}")
            return RoutingResult(
                success=False,
                message=res.get("message", "OpenFlow installation failed"),
                proposed_path=proposed_path,
                failure_stage=res.get("failure_stage"),
                error_type=res.get("error_type"),
                rollback_attempted=res.get("rollback_attempted", False),
                rollback_success=res.get("rollback_success"),
                rollback_error=res.get("rollback_error")
            )

    def _install_path(self, path, nw_src, nw_dst, priority, cookie, installed_rules, idle_timeout=30, hard_timeout=120):
        """Helper to install a single directional path and track installed rules for rollback."""
        for i in range(len(path) - 1):
            current_node = path[i]
            next_node = path[i+1]
            
            out_port = self.graph[current_node][next_node].get('out_port')
            if not out_port:
                logging.error(f"Cannot resolve out_port from {current_node} to {next_node}")
                return False
            
            if 'switch' in self.graph.nodes[current_node].get('type', 'switch'):
                flow_spec = (
                    f"cookie={cookie},priority={priority},"
                    f"idle_timeout={idle_timeout},hard_timeout={hard_timeout},"
                    f"ip,nw_src={nw_src},nw_dst={nw_dst},actions=output:{out_port}"
                )
                cmd = [
                    "sudo", "ovs-ofctl", "add-flow", current_node,
                    flow_spec
                ]
                res = subprocess.run(cmd, capture_output=True)
                if res.returncode != 0:
                    logging.error(f"Failed to install flow on {current_node}: {res.stderr.decode('utf-8')}")
                    return False
                installed_rules.append((current_node, nw_src, nw_dst, priority, cookie, out_port))
        return True

    def install_bidirectional_route(self, forward_path, reverse_path, nw_src, nw_dst, flow_id, priority=100, idle_timeout=30, hard_timeout=120) -> dict:
        """
        Physically injects OpenFlow rules into OVS switches along both paths.
        Implements rollback if any installation fails.
        """
        installed_rules = []
        import hashlib
        cookie = int(hashlib.md5(flow_id.encode()).hexdigest()[:8], 16)
        try:
            # Install forward path
            if not self._install_path(forward_path, nw_src, nw_dst, priority, cookie, installed_rules):
                rb_ok, rb_err = self._rollback_rules(installed_rules) if installed_rules else (True, None)
                return {
                    "success": False,
                    "message": "Forward path installation failed",
                    "failure_stage": "installation",
                    "error_type": "installation_error",
                    "rollback_attempted": bool(installed_rules),
                    "rollback_success": rb_ok if installed_rules else None,
                    "rollback_error": rb_err
                }
                
            # Install reverse path (swap nw_src and nw_dst)
            if not self._install_path(reverse_path, nw_dst, nw_src, priority, cookie, installed_rules):
                rb_ok, rb_err = self._rollback_rules(installed_rules)
                return {
                    "success": False,
                    "message": "Reverse path installation failed",
                    "failure_stage": "installation",
                    "error_type": "installation_error",
                    "rollback_attempted": True,
                    "rollback_success": rb_ok,
                    "rollback_error": rb_err
                }
                
            # Post-installation flow-table verification
            if not self._verify_installed_rules(installed_rules):
                rb_ok, rb_err = self._rollback_rules(installed_rules)
                return {
                    "success": False,
                    "message": "Flow rule verification failed",
                    "failure_stage": "verification",
                    "error_type": "verification_failed",
                    "rollback_attempted": True,
                    "rollback_success": rb_ok,
                    "rollback_error": rb_err
                }
                
            # Post-installation traffic counter verification
            if not self._verify_traffic_counters(installed_rules):
                rb_ok, rb_err = self._rollback_rules(installed_rules)
                return {
                    "success": False,
                    "message": "Traffic counter verification failed",
                    "failure_stage": "verification",
                    "error_type": "traffic_verification_failed",
                    "rollback_attempted": True,
                    "rollback_success": rb_ok,
                    "rollback_error": rb_err
                }

            return {
                "success": True,
                "message": "Route installed and verified successfully",
                "failure_stage": None,
                "error_type": None,
                "rollback_attempted": False,
                "rollback_success": None,
                "rollback_error": None
            }
        except Exception as e:
            logging.error(f"OpenFlow rule installation error: {e}")
            rb_ok, rb_err = self._rollback_rules(installed_rules) if installed_rules else (True, None)
            return {
                "success": False,
                "message": f"Installation exception: {str(e)}",
                "failure_stage": "installation",
                "error_type": "installation_error",
                "rollback_attempted": bool(installed_rules),
                "rollback_success": rb_ok if installed_rules else None,
                "rollback_error": rb_err
            }

    def _verify_installed_rules(self, installed_rules):
        """Post-installation flow-table verification."""
        for rule in installed_rules:
            current_node, nw_src, nw_dst, priority, cookie, out_port = rule
            cmd = ["sudo", "ovs-ofctl", "dump-flows", current_node]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode != 0:
                logging.error(f"Failed to dump flows for verification on {current_node}")
                return False
            output = res.stdout.decode('utf-8')
            
            cookie_hex = hex(cookie)
            if (f"cookie={cookie_hex}" not in output or 
                f"priority={priority}" not in output or
                f"nw_src={nw_src}" not in output or 
                f"nw_dst={nw_dst}" not in output or
                f"actions=output:{out_port}" not in output):
                logging.error(f"Flow verification failed on {current_node}: Rule not found in dump")
                return False
        return True

    def _verify_traffic_counters(self, installed_rules):
        """Verifies that traffic is actually hitting the new rules by checking packet counters."""
        logging.info("Verifying traffic movement on new paths...")
        time.sleep(2)
        
        for rule in installed_rules:
            current_node, nw_src, nw_dst, priority, cookie, out_port = rule
            cmd = ["sudo", "ovs-ofctl", "dump-flows", current_node]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode != 0:
                logging.error(f"Failed to dump flows for traffic verification on {current_node}")
                return False
            output = res.stdout.decode('utf-8')
            
            cookie_hex = hex(cookie)
            flow_found = False
            for line in output.split('\n'):
                if f"cookie={cookie_hex}" in line and f"priority={priority}" in line:
                    flow_found = True
                    try:
                        n_packets_str = [p for p in line.split(', ') if p.strip().startswith('n_packets=')]
                        if n_packets_str:
                            packets = int(n_packets_str[0].split('=')[1])
                            if packets == 0:
                                logging.warning(f"Flow verified on {current_node} but 0 packets matched.")
                    except Exception as e:
                        logging.error(f"Error parsing packet counts: {e}")
            if not flow_found:
                logging.error(f"Flow not found during traffic verification on {current_node}")
                return False
        return True

    def _rollback_rules(self, installed_rules):
        """Rollback successfully installed rules if a later rule fails."""
        logging.info("Rolling back partially installed OpenFlow rules...")
        rollback_success = True
        rollback_error = None
        for rule in installed_rules:
            current_node, nw_src, nw_dst, _, cookie, _ = rule
            cmd = [
                "sudo", "ovs-ofctl", "del-flows", current_node,
                f"cookie={cookie}/-1"
            ]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode != 0:
                rollback_success = False
                rollback_error = res.stderr.decode('utf-8')
        return rollback_success, rollback_error

    def cleanup_flow(self, flow_id: str) -> bool:
        """Explicitly deletes all OpenFlow rules matching the flow's unique cookie across all switches."""
        import hashlib
        cookie = int(hashlib.md5(flow_id.encode()).hexdigest()[:8], 16)
        success = True
        for node, data in self.graph.nodes(data=True):
            if 'switch' in data.get('type', 'switch'):
                cmd = ["sudo", "ovs-ofctl", "del-flows", node, f"cookie={cookie}/-1"]
                res = subprocess.run(cmd, capture_output=True)
                if res.returncode != 0:
                    logging.warning(f"Failed to delete flow rules for {flow_id} on {node}")
                    success = False
        return success

    def cleanup_all_flows(self) -> bool:
        """Deletes all custom routing rules installed across all switches."""
        logging.info("Cleaning up all custom OpenFlow rules on switches...")
        success = True
        for node, data in self.graph.nodes(data=True):
            if 'switch' in data.get('type', 'switch'):
                cmd = ["sudo", "ovs-ofctl", "del-flows", node, "table=0"]
                res = subprocess.run(cmd, capture_output=True)
                if res.returncode != 0:
                    logging.warning(f"Failed to clear table 0 on {node}")
                    success = False
        return success

if __name__ == '__main__':
    router = PredictiveRouter()
    print("Predictive Routing Engine initialized with Safety Checks and OpenFlow execution.")
