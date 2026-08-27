#!/usr/bin/env python3

import os
import sys
import time
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

import random
from mininet.log import info, setLogLevel

from network.topologies.small_test import create_small_network
from experiments.evidence_collector import capture_switch_state, record_policy, log_experiment_event


def run_normal():
    setLogLevel('info')
    seed = int(os.environ.get("EXPERIMENT_SEED", "42"))
    duration = int(os.environ.get("EXPERIMENT_DURATION", "60"))
    exp_id = os.environ.get("EXPERIMENT_ID", f"normal_seed{seed}")
    policy = os.environ.get("RESILINET_POLICY", "predictive")
    results_dir = Path(os.environ.get("RESILINET_RESULTS_DIR", str(Path(project_root) / "experiments" / "results" / exp_id)))
    traffic_dir = results_dir / "traffic"
    traffic_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    bw_mbps = round(rng.uniform(1.8, 2.2), 2)

    record_policy(policy, exp_id)
    info(f'*** Starting Normal Scenario (Seed: {seed}, Policy: {policy}, Target BW: {bw_mbps}Mbps)\n')
    net = create_small_network()

    # Capture baseline state while topology is fresh
    capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, stage="before")

    h1 = net.get('h1')
    h4 = net.get('h4')

    # Baseline ping
    ping_out_before = h1.cmd(f'ping -c 5 {h4.IP()}')
    with open(traffic_dir / "ping_before.txt", "w") as f:
        f.write(ping_out_before)

    # Start baseline traffic
    info('*** Starting baseline background traffic (iperf)\n')
    log_experiment_event(results_dir, "traffic_started_at", {"bandwidth_mbps": bw_mbps, "src": h1.IP(), "dst": h4.IP()})
    h4.cmd(f'iperf -s -u -i 1 > {traffic_dir}/iperf_server.log &')
    h1.cmd(f'iperf -c {h4.IP()} -u -b {bw_mbps}M -t {duration} > {traffic_dir}/iperf_client.log &')

    info('*** Running scenario...\n')
    # Normal scenario doesn't inject any additional faults
    time.sleep(duration)

    # Post-run ping
    ping_out_after = h1.cmd(f'ping -c 5 {h4.IP()}')
    with open(traffic_dir / "ping_after.txt", "w") as f:
        f.write(ping_out_after)

    # Capture post-run state before tearing down network
    info('*** Capturing post-run OpenFlow and port state...\n')
    capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, stage="after")
    log_experiment_event(results_dir, "experiment_finished_at")

    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    run_normal()
