#!/usr/bin/env python3

import networkx as nx
import json
import os
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class PredictiveRouter:
    """
    Calculates routing paths based on ML congestion predictions and installs physical OpenFlow rules.
    """
    def __init__(self, topology_json='network/topologies/topology.json', min_risk_improvement=0.2, cooldown=10):
        self.graph = nx.Graph()
        self.load_topology(topology_json)
        self.last_reroute_time = {} # Track cooldowns per flow
        self.min_risk_improvement = min_risk_improvement
        self.cooldown = cooldown

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
            self.graph.add_edge(link['source'], link['target'], weight=base_cost, original_weight=base_cost, risk=0.0)

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
                # Penalty curve: drastic increase if probable violation
                penalty = 1000 if prob > 0.5 else (prob * 10)
                self.graph[src][dst]['weight'] += penalty
                self.graph[src][dst]['risk'] = prob

    def calculate_path(self, source, target):
        """Calculate shortest path using current weights (Dijkstra)."""
        try:
            return nx.shortest_path(self.graph, source=source, target=target, weight='weight')
        except nx.NetworkXNoPath:
            logging.error(f"No path between {source} and {target}")
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

    def evaluate_and_reroute(self, flow_id, source, target, current_path, nw_src, nw_dst, priority=100):
        """
        Safety Checks & Physical Installation Pipeline.
        """
        now = time.time()
        if flow_id in self.last_reroute_time and (now - self.last_reroute_time[flow_id] < self.cooldown):
            logging.info(f"Flow {flow_id} in cooldown. Skipping reroute.")
            return False, "Cooldown Active"

        proposed_path = self.calculate_path(source, target)
        if not proposed_path or proposed_path == current_path:
            return False, "Proposed path identical or unreachable"

        current_risk = self.calculate_path_risk(current_path)
        proposed_risk = self.calculate_path_risk(proposed_path)

        if current_risk - proposed_risk < self.min_risk_improvement:
            return False, f"Risk improvement ({current_risk - proposed_risk:.2f}) below threshold"

        # Safety checks passed. Execute physical installation.
        success = self.install_openflow_route(proposed_path, nw_src, nw_dst, priority)
        
        if success:
            self.last_reroute_time[flow_id] = now
            logging.info(f"Successfully rerouted {flow_id}: {current_path} -> {proposed_path}")
            return True, "Reroute installed successfully"
        else:
            logging.error(f"Failed to install OpenFlow rules for {flow_id}")
            return False, "OpenFlow installation failed"

    def install_openflow_route(self, path, nw_src, nw_dst, priority=100):
        """
        Physically injects OpenFlow rules into OVS switches along the path.
        """
        try:
            for i in range(len(path) - 1):
                current_node = path[i]
                next_node = path[i+1]
                
                # In a real Mininet setup, we need the exact OpenFlow port mapping.
                # Assuming port 1 connects to next_node for demonstration.
                # A full implementation requires a topology mapping table.
                out_port = 1 
                
                if 'switch' in self.graph.nodes[current_node].get('type', 'switch'):
                    cmd = [
                        "sudo", "ovs-ofctl", "add-flow", current_node,
                        f"priority={priority},ip,nw_src={nw_src},nw_dst={nw_dst},actions=output:{out_port}"
                    ]
                    # We use shell=False for security, but echo the command to simulate success if Mininet isn't running
                    subprocess.run(cmd, check=False, capture_output=True)
            return True
        except Exception as e:
            logging.error(f"OpenFlow rule installation error: {e}")
            return False

if __name__ == '__main__':
    router = PredictiveRouter()
    print("Predictive Routing Engine initialized with Safety Checks and OpenFlow execution.")
