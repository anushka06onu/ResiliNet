#!/usr/bin/env python3

import os
import sys
import time
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from mininet.log import info, setLogLevel

from network.topologies.small_test import create_small_network


def run_normal():
    setLogLevel('info')
    seed = int(os.environ.get("EXPERIMENT_SEED", "42"))
    duration = int(os.environ.get("EXPERIMENT_DURATION", "60"))
    
    info(f'*** Starting Normal Scenario (Seed: {seed})\n')
    net = create_small_network()
    
    h1 = net.get('h1')
    h4 = net.get('h4')
    
    # Start baseline traffic
    info('*** Starting baseline background traffic (iperf)\n')
    h4.cmd('iperf -s -u -i 1 > /dev/null &')
    h1.cmd(f'iperf -c {h4.IP()} -u -b 2M -t {duration} > /dev/null &')
    
    info('*** Running scenario...\n')
    # Normal scenario doesn't inject any additional faults
    time.sleep(duration)
    
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    run_normal()
