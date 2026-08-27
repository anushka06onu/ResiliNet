#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import Controller, OVSKernelSwitch, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink
import time
import csv
import os
import json
import requests

def create_small_network():
    """Create a minimal network with 2 switches and 4 hosts."""
    net = Mininet(controller=RemoteController, switch=OVSKernelSwitch, link=TCLink)

    info('*** Adding controller\n')
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    info('*** Adding switches\n')
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')

    info('*** Adding hosts\n')
    h1 = net.addHost('h1', ip='10.0.0.1')
    h2 = net.addHost('h2', ip='10.0.0.2')
    h3 = net.addHost('h3', ip='10.0.0.3')
    h4 = net.addHost('h4', ip='10.0.0.4')

    info('*** Creating links\n')
    # Access links (fast, reliable)
    net.addLink(h1, s1, bw=100, delay='1ms', loss=0)
    net.addLink(h2, s1, bw=100, delay='1ms', loss=0)
    net.addLink(h3, s2, bw=100, delay='1ms', loss=0)
    net.addLink(h4, s2, bw=100, delay='1ms', loss=0)

    # Bottleneck link between switches
    net.addLink(s1, s2, bw=10, delay='10ms', loss=1, max_queue_size=100)

    info('*** Starting network\n')
    net.start()
    
    # Wait for switches to connect to the controller
    time.sleep(3)

    info('*** Exporting Live Topology\n')
    topology_data = {"nodes": [], "links": [], "mode": "LIVE LAB"}
    for node in net.switches:
        topology_data["nodes"].append({"id": node.name, "type": "switch"})
    for node in net.hosts:
        topology_data["nodes"].append({"id": node.name, "type": "host"})
        
    for link in net.links:
        src = link.intf1.node.name
        dst = link.intf2.node.name
        src_port = link.intf1.node.ports[link.intf1]
        dst_port = link.intf2.node.ports[link.intf2]
        topology_data["links"].append({
            "source": src,
            "source_port": str(src_port),
            "target": dst,
            "target_port": str(dst_port)
        })
        
    api_url = os.environ.get("RESILINET_API_URL", "http://127.0.0.1:8000")
    try:
        res = requests.post(f"{api_url}/api/v1/topology/ingest", json=topology_data, timeout=2)
        if res.status_code == 200:
            info('*** Topology successfully exported to API\n')
        else:
            info(f'*** API returned {res.status_code} on topology export\n')
    except Exception as e:
        info(f'*** Failed to export topology to API: {e}\n')

    # Ensure output directory exists
    os.makedirs('data_pipeline/data', exist_ok=True)
    
    info('*** Running tests and collecting data\n')
    results = []

    # Simple ping test
    info('--- Ping from h1 to h3\n')
    ping_out = h1.cmd('ping -c 5 10.0.0.3')
    info(ping_out)
    
    # Parse some basic info from ping (just for demonstration in Phase 2)
    packet_loss = "0"
    for line in ping_out.split('\n'):
        if 'packet loss' in line:
            packet_loss = line.split(',')[2].split('%')[0].strip()

    # iPerf test
    info('--- iPerf bandwidth test from h1 to h3\n')
    h3.cmd('iperf -s &') # Using iperf (v2) which is usually installed by default in mininet environments
    time.sleep(1)
    iperf_out = h1.cmd('iperf -c 10.0.0.3 -t 5')
    info(iperf_out)
    
    bandwidth = "0"
    for line in iperf_out.split('\n'):
        if 'Mbits/sec' in line:
            bandwidth = line.split()[-2]

    # Save to CSV
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    results.append({
        'timestamp': timestamp,
        'src': 'h1',
        'dst': 'h3',
        'ping_loss_percent': packet_loss,
        'iperf_bandwidth_mbps': bandwidth
    })

    csv_file = 'data_pipeline/data/small_test_results.csv'
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(results)
    
    info(f'*** Results saved to {csv_file}\n')
    return net

if __name__ == '__main__':
    setLogLevel('info')
    net = create_small_network()
    
    info('*** Stopping network\n')
    net.stop()
