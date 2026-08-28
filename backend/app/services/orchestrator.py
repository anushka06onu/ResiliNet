import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

# Ensure network is accessible
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from network.routing.predictive_routing import PredictiveRouter
from network.routing.policies import normalize_policy

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
        self.prediction_active = {}
        self.violation_active = {}
        self.active_episodes = {}
        from app.db.database import db_manager
        self.db_manager = db_manager

    def initialize_db(self):
        self.db_manager.initialize_db()

    def set_policy(self, policy: str):
        self.policy = normalize_policy(policy)
        self.router.set_policy(self.policy)
        logging.info(f"Orchestrator policy set to: {self.policy}")

    def begin_experiment(self, experiment_id: str, policy: str):
        """Set the active context and reset state for a new experiment."""
        self.active_experiment_id = experiment_id
        self.set_policy(policy)
        self.routing_decisions.clear()
        self.prediction_active.clear()
        self.violation_active.clear()
        self.active_episodes.clear()
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
        """Derives standard end-to-end flows between discovered hosts."""
        self.flows.clear()
        self.flow_locks.clear()

        for i in range(len(hosts)):
            for j in range(i + 1, len(hosts)):
                src_host = hosts[i]
                dst_host = hosts[j]
                flow_id = f"flow_{src_host}_{dst_host}"

                # Calculate shortest path in current graph
                try:
                    import networkx as nx
                    path = nx.shortest_path(self.router.graph, source=src_host, target=dst_host)
                except Exception:
                    path = [src_host, dst_host]

                self.flows[flow_id] = {
                    "flow_id": flow_id,
                    "src": src_host,
                    "dst": dst_host,
                    "current_path": path,
                    "state": "STABLE",
                    "sla_status": "Healthy"
                }
                self.flow_locks[flow_id] = threading.Lock()

    def handle_telemetry_event(self, event: dict):
        """Adapter for legacy event-based telemetry processing."""
        payload = event.get("payload", event)
        return self.ingest_telemetry(payload)

    def ingest_telemetry(self, payload: dict):
        """Processes incoming switch/link telemetry, updates risks, and handles state transitions."""
        link_id = payload.get("link_id")
        risk = payload.get("risk") if "risk" in payload else payload.get("predicted_risk")
        is_violation = payload.get("is_violation", False) or payload.get("is_violation_predicted", False)
        is_violation_actual = payload.get("is_violation_actual", False)
        loss = payload.get("loss_percent", 0.0) if "loss_percent" in payload else payload.get("loss_rate", 0.0)
        rtt = payload.get("control_plane_rtt_ms", 0.0) if "control_plane_rtt_ms" in payload else payload.get("latency_ms", 0.0)

        if link_id:
            try:
                try:
                    switch, port_str = link_id.split("-p")
                    port = int(port_str)
                except Exception:
                    switch, port = link_id, 1

                # Update risk on the specific edge
                edge_found = False
                target_switch = None
                for u, v, data in self.router.graph.edges(data=True):
                    if u == switch and data.get("out_port") == port:
                        if risk is not None:
                            self.router.update_link_predictions([{'source': u, 'target': v, 'congestion_prob': risk}])
                        edge_found = True
                        target_switch = v

                if link_id not in self.active_episodes and (is_violation or is_violation_actual):
                    self.active_episodes[link_id] = str(uuid.uuid4())[:8]
                episode_id = self.active_episodes.get(link_id)

                # Transition-based prediction event emission
                if is_violation and not self.prediction_active.get(link_id, False):
                    self.prediction_active[link_id] = True
                    self._log_experiment_event("prediction_threshold_crossed", link_id=link_id, episode_id=episode_id, details={"risk": risk})
                elif not is_violation and self.prediction_active.get(link_id, False):
                    self.prediction_active[link_id] = False
                    self._log_experiment_event("prediction_threshold_cleared", link_id=link_id, episode_id=episode_id, details={"risk": risk})

                # Transition-based SLA violation event emission
                if is_violation_actual and not self.violation_active.get(link_id, False):
                    self.violation_active[link_id] = True
                    self._log_experiment_event("sla_violation_started", link_id=link_id, episode_id=episode_id, details={"loss_percent": loss, "rtt_ms": rtt})
                elif not is_violation_actual and self.violation_active.get(link_id, False):
                    # Recovery confirmed by subsequent measured telemetry
                    self.violation_active[link_id] = False
                    self._log_experiment_event("sla_recovered", link_id=link_id, episode_id=episode_id, details={"loss_percent": loss, "rtt_ms": rtt})

                # Episode rotation: if prediction cleared and SLA recovered, close episode
                if not self.prediction_active.get(link_id, False) and not self.violation_active.get(link_id, False):
                    if link_id in self.active_episodes:
                        del self.active_episodes[link_id]

                if edge_found and target_switch:
                    evaluate = False
                    if self.policy == "predictive" and is_violation:
                        evaluate = True
                    elif self.policy == "reactive" and is_violation_actual:
                        evaluate = True

                    if evaluate:
                        self._evaluate_affected_flows(
                            switch,
                            target_switch,
                            is_violation_actual=is_violation_actual,
                            is_violation_predicted=bool(is_violation),
                            telemetry_link_id=link_id,
                            episode_id=episode_id
                        )

            except Exception as e:
                logging.error(f"Orchestrator failed to process telemetry for {link_id}: {e}")

    def _evaluate_affected_flows(self, congested_u, congested_v, is_violation_actual=False, is_violation_predicted=False, telemetry_link_id=None, episode_id=None):
        """Find flows crossing the congested directed edge and attempt to reroute them."""
        eff_link_id = telemetry_link_id or f"{congested_u}-{congested_v}"
        eff_episode_id = episode_id or self.active_episodes.get(eff_link_id) or str(uuid.uuid4())[:8]

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

                        risk_before = self.router.calculate_path_risk(switch_path)

                        # 1. Log reroute started BEFORE the rerouting operation
                        self._log_experiment_event(
                            "reroute_started",
                            flow_id=flow_id,
                            link_id=eff_link_id,
                            episode_id=eff_episode_id,
                            details={"risk_before": risk_before}
                        )

                        flow["state"] = "INSTALLING"

                        result = self.router.evaluate_and_reroute(
                            flow_id=flow_id,
                            source=switch_path[0] if switch_path else path[0],
                            target=switch_path[-1] if switch_path else path[-1],
                            current_path=switch_path,
                            nw_src=nw_src,
                            nw_dst=nw_dst,
                            is_violation_actual=is_violation_actual,
                            is_violation_predicted=is_violation_predicted
                        )
                        success = result.success
                        msg = result.message
                        proposed_path = result.proposed_path
                        failure_stage = result.failure_stage
                        error_type = result.error_type
                        risk_after = self.router.calculate_path_risk(proposed_path) if success and proposed_path else None
                        rollback_result = None
                        if result.rollback_attempted:
                            rollback_result = "success" if result.rollback_success else "failed"

                        flow["state"] = "VERIFYING"

                        # 2. Record decision
                        decision = {
                            "decision_id": str(uuid.uuid4()),
                            "experiment_id": self.active_experiment_id or "unknown",
                            "episode_id": eff_episode_id,
                            "flow_id": flow_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "risk_before": risk_before,
                            "risk_after": risk_after,
                            "original_path": path,
                            "proposed_path": proposed_path if success else None,
                            "safeguard_result": msg,
                            "installation_status": "INSTALLED" if (success or failure_stage == "verification") else "FAILED",
                            "verification_status": "VERIFIED" if success else ("FAILED" if failure_stage == "verification" else "SKIPPED"),
                            "outcome_status": "SUCCESS" if success else "FAILED",
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

                            # 3. Log reroute verified
                            self._log_experiment_event(
                                "reroute_verified_at",
                                flow_id=flow_id,
                                link_id=eff_link_id,
                                episode_id=eff_episode_id,
                                details={"new_path": new_full_path}
                            )
                        else:
                            if result.rollback_attempted:
                                self._log_experiment_event("rollback_started", flow_id=flow_id, link_id=eff_link_id, episode_id=eff_episode_id)
                                if result.rollback_success:
                                    flow["state"] = "STABLE"
                                    self._log_experiment_event("rollback_completed", flow_id=flow_id, link_id=eff_link_id, episode_id=eff_episode_id, details={"status": "SUCCESS"})
                                else:
                                    flow["state"] = "DEGRADED"
                                    self._log_experiment_event("rollback_completed", flow_id=flow_id, link_id=eff_link_id, episode_id=eff_episode_id, details={"status": "FAILED"})
                            else:
                                flow["state"] = "DEGRADED"
                            flow["sla_status"] = "Violated"

                            self._log_experiment_event(
                                "reroute_failed",
                                flow_id=flow_id,
                                link_id=eff_link_id,
                                episode_id=eff_episode_id,
                                details={"failure_stage": failure_stage, "error_type": error_type}
                            )

                        self.routing_decisions.append(decision)
                        try:
                            self.db_manager.record_decision(decision)
                        except Exception as e:
                            logging.error(f"Failed to persist decision to SQLite: {e}")
                finally:
                    lock.release()

    def _log_experiment_event(self, event_name: str, flow_id: Optional[str] = None, link_id: Optional[str] = None, episode_id: Optional[str] = None, details: Optional[dict] = None):
        """Append structured event to active experiment orchestrator_events.jsonl."""
        if not self.active_experiment_id:
            return
        import json
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[3]
        events_file = project_root / "experiments" / "results" / self.active_experiment_id / "orchestrator_events.jsonl"
        events_file.parent.mkdir(parents=True, exist_ok=True)
        event_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_name,
            "experiment_id": self.active_experiment_id,
            "episode_id": episode_id or "ep_default",
            "flow_id": flow_id,
            "link_id": link_id,
            "source": "orchestrator",
            "details": details or {}
        }
        try:
            with open(events_file, "a") as f:
                f.write(json.dumps(event_record) + "\n")
        except Exception as e:
            logging.error(f"Failed to log orchestrator event {event_name}: {e}")

# Singleton instance
orchestrator = Orchestrator()
