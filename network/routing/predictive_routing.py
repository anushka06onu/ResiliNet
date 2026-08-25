#!/usr/bin/env python3

import networkx as nx
import json
import os

class PredictiveRouter:
    """
    Calculates routing paths based on ML congestion predictions.
    """
    def __init__(self, topology_json='network/topologies/topology.json'):
        self.graph = nx.Graph()
        self.load_topology(topology_json)

    def load_topology(self, topology_json):
        if not os.path.exists(topology_json):
            print(f"Warning: {topology_json} not found. Router has an empty graph.")
            return
            
        with open(topology_json, 'r') as f:
            data = json.load(f)
            
        for node in data.get('nodes', []):
            self.graph.add_node(node['id'], type=node['type'])
            
        for link in data.get('links', []):
            # Base cost is inversely proportional to bandwidth (mocked as 1 if missing)
            base_cost = 1
            self.graph.add_edge(link['source'], link['target'], weight=base_cost, original_weight=base_cost)

    def update_link_predictions(self, predictions):
        """
        predictions: list of dicts [{'source': 's1', 'target': 's2', 'congestion_prob': 0.85}]
        """
        # Reset weights
        for u, v, d in self.graph.edges(data=True):
            d['weight'] = d['original_weight']
            
        # Inflate weights based on congestion probability
        for pred in predictions:
            src = pred['source']
            dst = pred['target']
            prob = pred['congestion_prob']
            
            if self.graph.has_edge(src, dst):
                # If probability of SLA violation > 0.5, drastically increase cost
                penalty = 1000 if prob > 0.5 else (prob * 10)
                self.graph[src][dst]['weight'] += penalty

    def calculate_path(self, source, target):
        """
        Calculate shortest path using current weights (Dijkstra).
        """
        try:
            path = nx.shortest_path(self.graph, source=source, target=target, weight='weight')
            return path
        except nx.NetworkXNoPath:
            print(f"No path between {source} and {target}")
            return None

if __name__ == '__main__':
    router = PredictiveRouter()
    print("Predictive Router initialized.")
    # Example usage
    # router.update_link_predictions([{'source': 's1', 'target': 's2', 'congestion_prob': 0.9}])
    # path = router.calculate_path('h1', 'server1')
