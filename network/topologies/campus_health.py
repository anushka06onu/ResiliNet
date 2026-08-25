#!/usr/bin/env python3

import json
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller, OVSKernelSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import os

class CampusHealthTopo(Topo):
    """
    Campus Health Network Topology
    
    Core Layer: c1, c2
    Distribution Layer: d1 (research), d2 (academic), d3 (healthcare)
    Access Layer: a1 (AI research), a2 (student lab), a3 (online class), 
                  a4 (telemedicine), a5 (general), a6 (backup)
    """
    def build(self):
        # 1. Add Switches
        # Core
        c1 = self.addSwitch('c1')
        c2 = self.addSwitch('c2')
        
        # Distribution
        d1 = self.addSwitch('d1') # Research
        d2 = self.addSwitch('d2') # Academic
        d3 = self.addSwitch('d3') # Healthcare
        
        # Access
        a1 = self.addSwitch('a1')
        a2 = self.addSwitch('a2')
        a3 = self.addSwitch('a3')
        a4 = self.addSwitch('a4')
        a5 = self.addSwitch('a5')
        a6 = self.addSwitch('a6')

        # 2. Add Hosts
        # Research Workloads
        h1 = self.addHost('h1', ip='10.0.1.1')
        h2 = self.addHost('h2', ip='10.0.1.2')
        h3 = self.addHost('h3', ip='10.0.1.3')
        
        # Student Users
        h4 = self.addHost('h4', ip='10.0.2.1')
        h5 = self.addHost('h5', ip='10.0.2.2')
        h6 = self.addHost('h6', ip='10.0.2.3')
        
        # Online Classrooms
        h7 = self.addHost('h7', ip='10.0.3.1')
        h8 = self.addHost('h8', ip='10.0.3.2')
        
        # Telemedicine Flows
        h9 = self.addHost('h9', ip='10.0.4.1')
        h10 = self.addHost('h10', ip='10.0.4.2')
        
        # General Browsing
        h11 = self.addHost('h11', ip='10.0.5.1')
        h12 = self.addHost('h12', ip='10.0.5.2')
        
        # Large Backup Flows
        h13 = self.addHost('h13', ip='10.0.6.1')
        h14 = self.addHost('h14', ip='10.0.6.2')
        
        # Servers (connected to Core)
        server1 = self.addHost('server1', ip='10.0.0.100')
        server2 = self.addHost('server2', ip='10.0.0.101')

        # 3. Add Links
        # Access -> Hosts (1Gbps, low latency)
        access_link_opts = dict(bw=1000, delay='1ms', loss=0)
        self.addLink(h1, a1, **access_link_opts)
        self.addLink(h2, a1, **access_link_opts)
        self.addLink(h3, a1, **access_link_opts)
        
        self.addLink(h4, a2, **access_link_opts)
        self.addLink(h5, a2, **access_link_opts)
        self.addLink(h6, a2, **access_link_opts)
        
        self.addLink(h7, a3, **access_link_opts)
        self.addLink(h8, a3, **access_link_opts)
        
        self.addLink(h9, a4, **access_link_opts)
        self.addLink(h10, a4, **access_link_opts)
        
        self.addLink(h11, a5, **access_link_opts)
        self.addLink(h12, a5, **access_link_opts)
        
        self.addLink(h13, a6, **access_link_opts)
        self.addLink(h14, a6, **access_link_opts)

        # Servers -> Core (10Gbps)
        core_link_opts = dict(bw=10000, delay='1ms', loss=0)
        self.addLink(server1, c1, **core_link_opts)
        self.addLink(server2, c2, **core_link_opts)

        # Access -> Distribution (1Gbps, slight delay)
        dist_link_opts = dict(bw=1000, delay='2ms', loss=0)
        self.addLink(a1, d1, **dist_link_opts)
        self.addLink(a2, d2, **dist_link_opts)
        self.addLink(a3, d2, **dist_link_opts)
        self.addLink(a4, d3, **dist_link_opts)
        self.addLink(a5, d1, **dist_link_opts)
        self.addLink(a6, d2, **dist_link_opts)

        # Distribution -> Core (Redundant Paths, varied metrics to allow routing logic)
        # Primary Paths (10Gbps)
        primary_route = dict(bw=10000, delay='2ms', loss=0)
        # Secondary/Backup Paths (1Gbps, higher delay)
        backup_route = dict(bw=1000, delay='5ms', loss=0)

        self.addLink(d1, c1, **primary_route)
        self.addLink(d1, c2, **backup_route)
        
        self.addLink(d2, c1, **backup_route)
        self.addLink(d2, c2, **primary_route)
        
        self.addLink(d3, c1, **primary_route)
        self.addLink(d3, c2, **backup_route)

        # Core -> Core
        self.addLink(c1, c2, bw=20000, delay='1ms', loss=0)

def export_topology_to_json(topo, filename):
    """Export the topology graph to JSON for the React dashboard."""
    graph = {
        'nodes': [],
        'links': []
    }
    
    for node in topo.nodes():
        node_type = 'switch' if node.startswith(('c', 'd', 'a')) else 'host'
        if node.startswith('server'):
            node_type = 'server'
            
        graph['nodes'].append({
            'id': node,
            'type': node_type
        })
        
    for link in topo.links(withKeys=False, withInfo=True):
        src, dst, info = link
        graph['links'].append({
            'source': src,
            'target': dst,
            'bandwidth': info.get('bw', 0),
            'delay': info.get('delay', '0ms')
        })
        
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(graph, f, indent=4)
    print(f"Topology exported to {filename}")

if __name__ == '__main__':
    setLogLevel('info')
    topo = CampusHealthTopo()
    
    # Export for dashboard
    export_topology_to_json(topo, 'frontend/public/topology.json')
    
    # Only start Mininet if we want to run the simulation interactively
    # For Phase 3, we just define the topology and export it.
    # net = Mininet(topo=topo, controller=Controller, switch=OVSKernelSwitch, link=TCLink)
    # net.start()
    # net.stop()
