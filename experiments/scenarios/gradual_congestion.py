#!/usr/bin/env python3

import os
import sys
import time
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from network.topologies.small_test import create_small_network
from mininet.log import setLogLevel, info

def run_gradual_congestion():
    setLogLevel('info')
    seed = int(os.environ.get("EXPERIMENT_SEED", "42"))
    duration = int(os.environ.get("EXPERIMENT_DURATION", "60"))
    
    info(f'*** Starting Gradual Congestion Scenario (Seed: {seed})\n')
    net = create_small_network()
    
    h1 = net.get('h1')
    h4 = net.get('h4')
    
    # Start baseline traffic
    info('*** Starting baseline background traffic (iperf)\n')
    h4.cmd('iperf -s -u -i 1 > /dev/null &')
    h1.cmd(f'iperf -c {h4.IP()} -u -b 2M -t {duration} > /dev/null &')
    
    # Wait some time, then gradually increase delay and loss on s1-s2
    info('*** Running baseline phase...\n')
    time.sleep(duration // 3)
    
    info('*** Injecting gradual congestion...\n')
    # Use tc to add delay and loss
    # interface s1-eth3 connects to s2
    s1 = net.get('s1')
    s1.cmd('tc qdisc change dev s1-eth3 root netem delay 15ms loss 2%')
    
    time.sleep(duration // 3)
    info('*** Worsening congestion...\n')
    s1.cmd('tc qdisc change dev s1-eth3 root netem delay 25ms loss 5%')
    
    time.sleep(duration - (duration // 3) * 2)
    
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    run_gradual_congestion()
