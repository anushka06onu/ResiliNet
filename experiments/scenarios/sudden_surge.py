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


def run_sudden_surge():
    setLogLevel('info')
    seed = int(os.environ.get("EXPERIMENT_SEED", "42"))
    duration = int(os.environ.get("EXPERIMENT_DURATION", "60"))
    exp_id = os.environ.get("EXPERIMENT_ID", f"sudden_surge_seed{seed}")
    policy = os.environ.get("RESILINET_POLICY", "predictive")
    results_dir = Path(project_root) / "experiments" / "results"

    record_policy(policy, exp_id)
    info(f'*** Starting Sudden Surge Scenario (Seed: {seed}, Policy: {policy})\n')
    net = create_small_network()

    # Capture baseline state while topology is fresh
    capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, exp_id, stage="before")

    h1 = net.get('h1')
    h2 = net.get('h2')
    h4 = net.get('h4')

    # Start baseline traffic
    info('*** Starting baseline background traffic (iperf)\n')
    h4.cmd('iperf -s -u -i 1 > /dev/null &')
    h1.cmd(f'iperf -c {h4.IP()} -u -b 2M -t {duration} > /dev/null &')

    info('*** Running baseline phase...\n')
    time.sleep(duration // 2)

    info('*** Injecting sudden surge...\n')
    # Sudden surge: start massive traffic from h2 to h4
    h2.cmd(f'iperf -c {h4.IP()} -u -b 20M -t {duration // 2} > /dev/null &')

    time.sleep(duration - (duration // 2))

    # Capture post-surge state before tearing down network
    info('*** Capturing post-surge OpenFlow and port state...\n')
    capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, exp_id, stage="after")

    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    run_sudden_surge()
