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
from experiments.evidence_collector import (
    capture_switch_state,
    record_policy,
    log_experiment_event,
    apply_and_verify_netem
)


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
    results_dir = Path(os.environ.get("RESILINET_RESULTS_DIR", str(Path(project_root) / "experiments" / "results" / exp_id)))
    traffic_dir = results_dir / "traffic"
    traffic_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    crit_bw = round(rng.uniform(0.9, 1.1), 2)
    video_bw = round(rng.uniform(2.8, 3.2), 2)
    bulk_bw = round(rng.uniform(4.5, 5.5), 2)

    record_policy(policy, exp_id)
    info(f'*** Starting Concurrent Competing Flows Scenario (Seed: {seed}, Duration: {duration}s, Policy: {policy})\n')

    net = None
    try:
        net = create_small_network()

        # Capture baseline state while topology is fresh
        capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, stage="before")

        h1 = net.get('h1')
        h2 = net.get('h2') if 'h2' in net else h1
        h3 = net.get('h3') if 'h3' in net else h1
        h4 = net.get('h4')
        s1 = net.get('s1')

        # Baseline latency measurement
        ping_out_before = h1.cmd(f'ping -c 5 {h4.IP()}')
        with open(traffic_dir / "ping_before.txt", "w") as f:
            f.write(ping_out_before)

        # Start servers on destination
        info('*** Initializing iperf receiver servers on h4\n')
        h4.cmd(f'iperf -s -u -p 5001 -i 1 > {traffic_dir}/iperf_critical_server.log &')
        h4.cmd(f'iperf -s -u -p 5002 -i 1 > {traffic_dir}/iperf_video_server.log &')
        h4.cmd(f'iperf -s -u -p 5003 -i 1 > {traffic_dir}/iperf_bulk_server.log &')

        # Phase 1: Normal concurrent operation
        info('*** Phase 1: Normal concurrent operation (Critical + Video + Bulk)\n')
        log_experiment_event(results_dir, "traffic_started_at", {"critical_bw": crit_bw, "video_bw": video_bw, "bulk_bw": bulk_bw})
        h1.cmd(f'iperf -c {h4.IP()} -u -p 5001 -b {crit_bw}M -t {duration} > {traffic_dir}/iperf_critical_client.log &')
        if h2 != h1:
            h2.cmd(f'iperf -c {h4.IP()} -u -p 5002 -b {video_bw}M -t {duration} > {traffic_dir}/iperf_video_client.log &')
        if h3 != h1:
            h3.cmd(f'iperf -c {h4.IP()} -u -p 5003 -b {bulk_bw}M -t {duration} > {traffic_dir}/iperf_bulk_client.log &')

        time.sleep(duration // 3)

        # Phase 2: Bulk flow surge creating contention
        info('*** Phase 2: Injecting background bulk flow surge on bottleneck link\n')
        apply_and_verify_netem(s1, "s1-eth3", 20.0, 3.0, results_dir, "congestion_injected_at", stage=2)

        time.sleep(duration // 3)

        # Phase 3: High contention phase
        info('*** Phase 3: High contention phase\n')
        apply_and_verify_netem(s1, "s1-eth3", 35.0, 8.0, results_dir, "congestion_worsened_at", stage=3)

        time.sleep(duration - (duration // 3) * 2)

        # Post-intervention latency measurement
        ping_out_after = h1.cmd(f'ping -c 5 {h4.IP()}')
        with open(traffic_dir / "ping_after.txt", "w") as f:
            f.write(ping_out_after)

        # Capture post-intervention state before tearing down network
        info('*** Capturing post-intervention OpenFlow and port state...\n')
        capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, stage="after")
        log_experiment_event(results_dir, "measurement_finished_at")
    finally:
        if net is not None:
            log_experiment_event(results_dir, "topology_teardown_started_at")
            info('*** Stopping network\n')
            net.stop()
            log_experiment_event(results_dir, "topology_teardown_completed_at")


if __name__ == '__main__':
    run_concurrent_flows()
