import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone

# Ensure network is accessible
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from network.routing.predictive_routing import PredictiveRouter

logging.basicConfig(level=logging.INFO)

class Orchestrator:
    """
    Coordinates between ML telemetry ingestion, state tracking, and routing logic.
    """
    def __init__(self):
        # We load a topology at startup or receive it via ingest endpoint
        import os
        from pathlib import Path
        project_root = Path(os.path.dirname(__file__)).resolve().parents[2]
        topology_path = project_root / 'frontend' / 'public' / 'topology.json'


        self.router = PredictiveRouter(topology_json=str(topology_path))
        self.flows = {}
        self.flow_locks = {}
        self.routing_decisions = []
        self.policy = "predictive"
        self.active_experiment_id = None

        self.routing_decisions = []
        self.policy = "predictive"
        self.active_experiment_id = None
        from app.db.database import db_manager
        self.db_manager = db_manager

    def initialize_db(self):
        self.db_manager.initialize_db()

    def set_policy(self, policy: str):
        self.policy = policy
        logging.info(f"Orchestrator policy set to: {self.policy}")

    def begin_experiment(self, experiment_id: str, policy: str):
        """Set the active context and reset state for a new experiment."""
        self.active_experiment_id = experiment_id
        self.set_policy(policy)
        self.routing_decisions.clear()
        # Reset flow SLA states
        for flow in self.flows.values():
            flow["state"] = "STABLE"
            flow["sla_status"] = "Healthy"
        logging.info(f"Orchestrator began experiment: {self.active_experiment_id} with policy {self.policy}")


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
        """Auto-generate baseline flows between discovered hosts dynamically."""
        sorted_hosts = sorted(hosts)
        n = len(sorted_hosts)
        expected_pairs = []
        for i in range(n // 2):
            src = sorted_hosts[i]
            dst = sorted_hosts[n - 1 - i]
            tier = "Critical" if i == 0 else "Background"
            expected_pairs.append((src, dst, tier))

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
            "state": "STABLE",
            "sla_status": "Healthy",
            "current_path": initial_path
        }
        self.flow_locks[flow_id] = threading.Lock()
        logging.info(f"Registered {tier} flow {flow_id} from {src} to {dst}: {initial_path}")

    def handle_telemetry_event(self, event):
        """Process a telemetry event, update risks, and trigger routing if necessary."""
        payload = event.get("payload", {})
        link_id = payload.get("link_id")
        risk = payload.get("predicted_risk")
        is_violation = payload.get("is_violation_predicted")
        is_violation_actual = payload.get("is_violation_actual", False)

        if link_id:
            try:
                switch, port_str = link_id.split("-p")
                port = int(port_str)

                # Update risk on the specific edge
                edge_found = False
                target_switch = None
                for u, v, data in self.router.graph.edges(data=True):
                    if u == switch and data.get("out_port") == port:
                        if risk is not None:
                            self.router.update_link_predictions([{'source': u, 'target': v, 'congestion_prob': risk}])
                        edge_found = True
                        target_switch = v

                if edge_found and target_switch:
                    evaluate = False
                    if self.policy == "predictive" and is_violation:
                        evaluate = True
                    elif self.policy == "reactive" and is_violation_actual:
                        evaluate = True

                    if evaluate:
                        self._evaluate_affected_flows(switch, target_switch)

            except Exception as e:
                logging.error(f"Orchestrator failed to process telemetry for {link_id}: {e}")

    def _evaluate_affected_flows(self, congested_u, congested_v):
        """Find flows crossing the congested directed edge and attempt to reroute them."""
        for flow_id, flow in self.flows.items():
            # Attempt to acquire lock without blocking so we don't hold up other evaluations
            lock = self.flow_locks.get(flow_id)
            if lock and lock.acquire(blocking=False):
                try:
                    if flow["state"] not in ["STABLE", "DEGRADED"]:
                        continue

                    path = flow["current_path"]

                    # Check if the specific directed edge is in the path
                    edge_in_path = False
                    for i in range(len(path) - 1):
                        if path[i] == congested_u and path[i+1] == congested_v:
                            edge_in_path = True
                            break

                    if edge_in_path:
                        # Trigger reroute evaluation
                        flow["state"] = "EVALUATING"

                        # Strip host nodes from path for the router
                        switch_path = [n for n in path if "h" not in n]

                        # Derive IPs dynamically from host names (e.g. h1 -> 10.0.0.1)
                        try:
                            import re
                            src_num = re.search(r'\d+', flow['src']).group()
                            dst_num = re.search(r'\d+', flow['dst']).group()
                            nw_src = f"10.0.0.{src_num}"
                            nw_dst = f"10.0.0.{dst_num}"
                        except Exception:
                            # Fallback if names don't match pattern
                            nw_src = "10.0.0.1"
                            nw_dst = "10.0.0.2"

                        logging.info(f"Flow {flow_id} crosses congested edge {congested_u}->{congested_v}. Evaluating reroute...")

                        risk_before = self.router.calculate_path_risk(switch_path)

                        flow["state"] = "INSTALLING"

                        result = self.router.evaluate_and_reroute(
                            flow_id=flow_id,
                            source=switch_path[0] if switch_path else path[0],
                            target=switch_path[-1] if switch_path else path[-1],
                            current_path=switch_path,
                            nw_src=nw_src,
                            nw_dst=nw_dst
                        )
                        success = result.success
                        msg = result.message
                        proposed_path = result.proposed_path

                        flow["state"] = "VERIFYING"

                        # Note: In a real async system we'd wait here, but for this mock we assume evaluate_and_reroute does it

                        risk_after = self.router.calculate_path_risk(proposed_path) if success and proposed_path else None

                        failure_stage = result.failure_stage
                        error_type = result.error_type
                        rollback_result = None
                        if result.rollback_attempted:
                            rollback_result = "success" if result.rollback_success else "failed"

                        # Record decision
                        decision = {
                            "decision_id": str(uuid.uuid4()),
                            "experiment_id": self.active_experiment_id or "unknown",
                            "flow_id": flow_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "risk_before": risk_before,
                            "risk_after": risk_after,
                            "original_path": path,
                            "proposed_path": proposed_path if success else (proposed_path if proposed_path else None),
                            "safeguard_result": msg,
                            "installation_status": "success" if (success or failure_stage == "verification") else "failed",
                            "verification_status": "success" if success else ("failed" if failure_stage == "verification" else "skipped"),
                            "outcome_status": "success" if success else "failed",
                            "failure_stage": failure_stage,
                            "error_type": error_type,
                            "rollback_result": rollback_result
                        }

                        if success:
                            flow["sla_status"] = "Rerouted"
                            new_full_path = proposed_path.copy()
                            if path[0].startswith("h"): new_full_path.insert(0, path[0])
                            if path[-1].startswith("h"): new_full_path.append(path[-1])
                            flow["current_path"] = new_full_path
                            flow["state"] = "STABLE"
                        else:
                            if result.rollback_attempted:
                                if result.rollback_success:
                                    flow["state"] = "ROLLBACK_COMPLETE"
                                    # Recovery transition to stable on original path
                                    flow["state"] = "STABLE"
                                else:
                                    flow["state"] = "DEGRADED"
                            else:
                                flow["state"] = "DEGRADED"
                            flow["sla_status"] = "Violated"

                        self.routing_decisions.append(decision)
                        try:
                            self.db_manager.record_decision(decision)
                        except Exception as e:
                            logging.error(f"Failed to persist decision to SQLite: {e}")
                finally:

                    lock.release()

# Singleton instance
orchestrator = Orchestrator()
