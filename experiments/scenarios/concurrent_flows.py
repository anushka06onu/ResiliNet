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
from experiments.evidence_collector import capture_switch_state, record_policy


def run_concurrent_flows():
    """
    Scenario with 3 concurrent traffic classes competing over the bottleneck link:
    1. Critical Flow (Tier 1, Telemedicine): h1 -> h4 (1 Mbps, strict QoS)
    2. Video Flow (Tier 2, Education): h2 -> h4 (4 Mbps, moderate QoS)
    3. Bulk Flow (Tier 3, Background): h3 -> h4 (8 Mbps bulk saturation)
    """
    setLogLevel('info')
    seed = int(os.environ.get("EXPERIMENT_SEED", "42"))
    duration = int(os.environ.get("EXPERIMENT_DURATION", "60"))
    exp_id = os.environ.get("EXPERIMENT_ID", f"concurrent_flows_seed{seed}")
    policy = os.environ.get("RESILINET_POLICY", "predictive")
    results_dir = Path(project_root) / "experiments" / "results"

    record_policy(policy, exp_id)
    info(f'*** Starting Concurrent Competing Flows Scenario (Seed: {seed}, Duration: {duration}s, Policy: {policy})\n')
    net = create_small_network()

    # Capture baseline state while topology is fresh
    capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, exp_id, stage="before")

    h1 = net.get('h1')
    h2 = net.get('h2') if 'h2' in net else h1
    h3 = net.get('h3') if 'h3' in net else h1
    h4 = net.get('h4')

    # Start servers on destination
    info('*** Initializing iperf receiver servers on h4\n')
    h4.cmd('iperf -s -u -p 5001 -i 1 > /dev/null &')
    h4.cmd('iperf -s -u -p 5002 -i 1 > /dev/null &')
    h4.cmd('iperf -s -u -p 5003 -i 1 > /dev/null &')

    # Phase 1: Normal concurrent operation
    info('*** Phase 1: Normal concurrent operation (Critical + Video + Bulk)\n')
    h1.cmd(f'iperf -c {h4.IP()} -u -p 5001 -b 1M -t {duration} > /dev/null &')
    if h2 != h1:
        h2.cmd(f'iperf -c {h4.IP()} -u -p 5002 -b 3M -t {duration} > /dev/null &')
    if h3 != h1:
        h3.cmd(f'iperf -c {h4.IP()} -u -p 5003 -b 5M -t {duration} > /dev/null &')

    time.sleep(duration // 3)

    # Phase 2: Bulk flow surge creating contention
    info('*** Phase 2: Injecting background bulk flow surge on bottleneck link\n')
    s1 = net.get('s1')
    s1.cmd('tc qdisc change dev s1-eth3 root netem delay 20ms loss 3%')

    time.sleep(duration // 3)

    # Phase 3: High contention phase
    info('*** Phase 3: High contention phase\n')
    s1.cmd('tc qdisc change dev s1-eth3 root netem delay 35ms loss 8%')

    time.sleep(duration - (duration // 3) * 2)

    # Capture post-intervention state before tearing down network
    info('*** Capturing post-intervention OpenFlow and port state...\n')
    capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, exp_id, stage="after")

    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    run_concurrent_flows()
