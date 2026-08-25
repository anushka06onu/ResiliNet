#!/usr/bin/env python3

from mininet.log import setLogLevel, info
import time
import sys
import os

# Ensure we can import from topologies and traffic
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from network.topologies.campus_health import CampusHealthTopo
from network.traffic.critical_flows import start_telemedicine_flow
from network.traffic.video_flows import start_video_flow
from network.traffic.background_flows import start_background_flow
from mininet.net import Mininet
from mininet.node import Controller, OVSKernelSwitch
from mininet.link import TCLink

def run_scenario():
    """
    Scenario F: Competing priorities
    Critical, high-priority and background flows share a bottleneck
    """
    info('*** Initializing Campus Health Topology\n')
    topo = CampusHealthTopo()
    net = Mininet(topo=topo, controller=Controller, switch=OVSKernelSwitch, link=TCLink)
    
    info('*** Starting Network\n')
    net.start()
    
    info('*** Warming up the network\n')
    time.sleep(2)
    
    info('*** Starting flows\n')
    
    # 1. Background flow (Student Lab to Backup Server) - Best Effort
    # Using the secondary path intentionally or letting shortest path decide
    start_background_flow(net, 'h4', 'server2', bw='20M')
    
    # 2. Video Flow (Online class to App Server) - High Priority
    start_video_flow(net, 'h7', 'server1', bw='5M')
    
    # 3. Telemedicine Flow (Telemedicine Station to App Server) - Critical Priority
    # Start slightly later to observe the impact of existing background traffic
    time.sleep(5)
    start_telemedicine_flow(net, 'h9', 'server1', bw='3M')
    
    info('*** Simulation running for 30 seconds...\n')
    time.sleep(30)
    
    info('*** Stopping Network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    # Uncomment to actually run it (requires Linux/Mininet)
    # run_scenario()
