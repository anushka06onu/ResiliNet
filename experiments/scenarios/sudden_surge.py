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


def run_sudden_surge():
    setLogLevel('info')
    seed = int(os.environ.get("EXPERIMENT_SEED", "42"))
    duration = int(os.environ.get("EXPERIMENT_DURATION", "60"))
    exp_id = os.environ.get("EXPERIMENT_ID", f"sudden_surge_seed{seed}")
    policy = os.environ.get("RESILINET_POLICY", "predictive")
    results_dir = Path(os.environ.get("RESILINET_RESULTS_DIR", str(Path(project_root) / "experiments" / "results" / exp_id)))
    traffic_dir = results_dir / "traffic"
    traffic_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    base_bw = round(rng.uniform(1.8, 2.2), 2)
    surge_bw = round(rng.uniform(18.0, 22.0), 1)

    record_policy(policy, exp_id)
    info(f'*** Starting Sudden Surge Scenario (Seed: {seed}, Policy: {policy}, Base: {base_bw}M, Surge: {surge_bw}M)\n')

    net = None
    try:
        net = create_small_network()

        # Capture baseline state while topology is fresh
        capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, stage="before")

        h1 = net.get('h1')
        h2 = net.get('h2')
        h4 = net.get('h4')

        # Baseline ping
        ping_out_before = h1.cmd(f'ping -c 5 {h4.IP()}')
        with open(traffic_dir / "ping_before.txt", "w") as f:
            f.write(ping_out_before)

        # Start baseline traffic
        info('*** Starting baseline background traffic (iperf)\n')
        log_experiment_event(results_dir, "traffic_started_at", {"base_bw_mbps": base_bw, "src": h1.IP(), "dst": h4.IP()})
        h4.cmd(f'iperf -s -u -i 1 > {traffic_dir}/iperf_server.log &')
        h1.cmd(f'iperf -c {h4.IP()} -u -b {base_bw}M -t {duration} > {traffic_dir}/iperf_client.log &')

        info('*** Running baseline phase...\n')
        time.sleep(duration // 2)

        info(f'*** Injecting sudden surge ({surge_bw}M from h2)...\n')
        log_experiment_event(results_dir, "congestion_injected_at", {"surge_bw_mbps": surge_bw, "src": h2.IP(), "dst": h4.IP()})
        # Sudden surge: start massive traffic from h2 to h4
        h2.cmd(f'iperf -c {h4.IP()} -u -b {surge_bw}M -t {duration // 2} > {traffic_dir}/iperf_surge_client.log &')

        time.sleep(duration - (duration // 2))

        # Post-surge ping
        ping_out_after = h1.cmd(f'ping -c 5 {h4.IP()}')
        with open(traffic_dir / "ping_after.txt", "w") as f:
            f.write(ping_out_after)

        # Capture post-surge state before tearing down network
        info('*** Capturing post-surge OpenFlow and port state...\n')
        capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, stage="after")
        log_experiment_event(results_dir, "measurement_finished_at")
    finally:
        if net is not None:
            log_experiment_event(results_dir, "topology_teardown_started_at")
            info('*** Stopping network\n')
            net.stop()
            log_experiment_event(results_dir, "topology_teardown_completed_at")


if __name__ == '__main__':
    run_sudden_surge()
