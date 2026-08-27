import uuid
from datetime import datetime
import sys
import os

# Ensure network is accessible
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from network.routing.predictive_routing import PredictiveRouter
import logging

class Orchestrator:
    def __init__(self):
        self.router = PredictiveRouter(topology_json='frontend/public/topology.json')
        self.flows = {}
        self.routing_decisions = []

    def load_topology(self, topo_data):
        """Update the internal PredictiveRouter graph dynamically and discover flows."""
        self.router.graph.clear()
        
        hosts = []
        for node in topo_data.get('nodes', []):
            node_type = node.get('type', 'switch')
            self.router.graph.add_node(node['id'], type=node_type)
            if node_type == 'host':
                hosts.append(node['id'])
            
        for link in topo_data.get('links', []):
            base_cost = 1
            src = link['source']
            dst = link['target']
            src_port = link.get('source_port')
            dst_port = link.get('target_port')
            
            self.router.graph.add_edge(src, dst, weight=base_cost, original_weight=base_cost, risk=0.0, out_port=src_port)
            self.router.graph.add_edge(dst, src, weight=base_cost, original_weight=base_cost, risk=0.0, out_port=dst_port)

        # Derive initial flows from hosts
        self._derive_flows_from_topology(hosts)

    def _derive_flows_from_topology(self, hosts):
        """Auto-generate baseline flows between discovered hosts."""
        # Simple heuristic: pair hosts based on ID or just connect specific ones
        # For small_test: h1->h4 and h2->h3 if they exist
        expected_pairs = [("h1", "h4", "Critical"), ("h2", "h3", "Background")]
        
        for idx, (src, dst, tier) in enumerate(expected_pairs):
            if src in hosts and dst in hosts:
                path = self.router.calculate_path(src, dst)
                if path:
                    flow_id = f"f_{idx+1}"
                    # Ensure we don't overwrite if it already exists to avoid resetting state
                    if flow_id not in self.flows:
                        self.register_flow(flow_id, src, dst, path, tier)

    def register_flow(self, flow_id, src, dst, initial_path, tier="Standard"):
        self.flows[flow_id] = {
            "flow_id": flow_id,
            "src": src,
            "dst": dst,
            "tier": tier,
            "sla_status": "Healthy",
            "current_path": initial_path,
            "state": "ACTIVE"
        }

    def handle_telemetry_event(self, event):
        """Process a telemetry event, update risks, and trigger routing if necessary."""
        payload = event.get("payload", {})
        link_id = payload.get("link_id")
        risk = payload.get("predicted_risk")
        is_violation = payload.get("is_violation_predicted")
        
        if link_id and risk is not None:
            # We expect link_id like s1-p1, which doesn't directly map to src->dst.
            # We need to find the edge that has this out_port.
            # For simplicity, if we know the switch (s1) and port (1), we can find the target.
            try:
                switch, port_str = link_id.split("-p")
                port = int(port_str)
                
                # Update risk on the specific edge
                edge_found = False
                for u, v, data in self.router.graph.edges(data=True):
                    if u == switch and data.get("out_port") == port:
                        # update_link_predictions expects a list of dicts
                        self.router.update_link_predictions([{'source': u, 'target': v, 'congestion_prob': risk}])
                        edge_found = True
                        
                if edge_found and is_violation:
                    self._evaluate_affected_flows(switch)
            except Exception as e:
                logging.error(f"Orchestrator failed to process telemetry for {link_id}: {e}")
                
    def _evaluate_affected_flows(self, congested_switch):
        """Find flows crossing the congested switch and attempt to reroute them."""
        for flow_id, flow in self.flows.items():
            if flow["state"] != "ACTIVE":
                continue
                
            path = flow["current_path"]
            if congested_switch in path:
                # Trigger reroute evaluation
                flow["state"] = "EVALUATING"
                
                # Mock IPs (in a real system, these would be in the flow registry)
                nw_src = "10.0.0.1" if flow["src"] == "h1" else "10.0.0.2"
                nw_dst = "10.0.0.4" if flow["dst"] == "h4" else "10.0.0.3"
                
                logging.info(f"Flow {flow_id} crosses congested switch {congested_switch}. Evaluating reroute...")
                success, msg, proposed_path = self.router.evaluate_and_reroute(
                    flow_id=flow_id,
                    source=path[0],
                    target=path[-1],
                    current_path=path,
                    nw_src=nw_src,
                    nw_dst=nw_dst
                )
                
                # Record decision
                decision = {
                    "decision_id": str(uuid.uuid4()),
                    "experiment_id": "live_run",
                    "flow_id": flow_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "risk_before": None, # Could extract from router
                    "risk_after": None,
                    "original_path": path,
                    "proposed_path": None,
                    "safeguard_result": msg,
                    "installation_status": "success" if success else "failed",
                    "verification_status": "success" if success else "failed",
                    "outcome_status": "success" if success else "failed"
                }
                
                if success:
                    # Update flow path (ideally we fetch proposed_path from router, but router evaluate_and_reroute doesn't return it yet)
                    # We will just mark it as ACTIVE again for now.
                    flow["sla_status"] = "Rerouted"
                    flow["current_path"] = proposed_path
                    decision["proposed_path"] = proposed_path
                else:
                    flow["sla_status"] = "Violated"
                    
                flow["state"] = "ACTIVE"
                self.routing_decisions.append(decision)

# Singleton instance
orchestrator = Orchestrator()
