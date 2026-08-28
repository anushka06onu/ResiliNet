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


def run_gradual_congestion():
    setLogLevel('info')
    seed = int(os.environ.get("EXPERIMENT_SEED", "42"))
    duration = int(os.environ.get("EXPERIMENT_DURATION", "60"))
    exp_id = os.environ.get("EXPERIMENT_ID", f"gradual_congestion_seed{seed}")
    policy = os.environ.get("RESILINET_POLICY", "predictive")
    results_dir = Path(os.environ.get("RESILINET_RESULTS_DIR", str(Path(project_root) / "experiments" / "results" / exp_id)))
    traffic_dir = results_dir / "traffic"
    traffic_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    bw_mbps = round(rng.uniform(1.8, 2.2), 2)
    phase1_delay_ms = round(rng.uniform(14.0, 16.0), 1)
    phase1_loss_pct = round(rng.uniform(1.8, 2.2), 1)
    phase2_delay_ms = round(rng.uniform(23.0, 27.0), 1)
    phase2_loss_pct = round(rng.uniform(4.5, 5.5), 1)

    record_policy(policy, exp_id)
    info(f'*** Starting Gradual Congestion Scenario (Seed: {seed}, Policy: {policy}, Target BW: {bw_mbps}Mbps)\n')

    net = None
    try:
        net = create_small_network()

        # Capture baseline state while topology is fresh
        capture_switch_state(["s1", "s2", "s3", "s4"], results_dir, stage="before")

        h1 = net.get('h1')
        h4 = net.get('h4')
        s1 = net.get('s1')

        # Baseline latency measurement (ping before)
        ping_out_before = h1.cmd(f'ping -c 5 {h4.IP()}')
        with open(traffic_dir / "ping_before.txt", "w") as f:
            f.write(ping_out_before)

        # Start baseline traffic
        info(f'*** Starting baseline background traffic (iperf {bw_mbps}M)\n')
        log_experiment_event(results_dir, "traffic_started_at", {"bandwidth_mbps": bw_mbps, "src": h1.IP(), "dst": h4.IP()})
        h4.cmd(f'iperf -s -u -i 1 > {traffic_dir}/iperf_server.log &')
        h1.cmd(f'iperf -c {h4.IP()} -u -b {bw_mbps}M -t {duration} > {traffic_dir}/iperf_client.log &')

        # Wait some time, then gradually increase delay and loss on s1-s2
        info('*** Running baseline phase...\n')
        time.sleep(duration // 3)

        info(f'*** Injecting gradual congestion (delay: {phase1_delay_ms}ms, loss: {phase1_loss_pct}%)...\n')
        apply_and_verify_netem(s1, "s1-eth3", phase1_delay_ms, phase1_loss_pct, results_dir, "congestion_injected_at", stage=1)

        time.sleep(duration // 3)
        info(f'*** Worsening congestion (delay: {phase2_delay_ms}ms, loss: {phase2_loss_pct}%)...\n')
        apply_and_verify_netem(s1, "s1-eth3", phase2_delay_ms, phase2_loss_pct, results_dir, "congestion_worsened_at", stage=2)

        time.sleep(duration - (duration // 3) * 2)

        # Post-intervention latency measurement (ping after)
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
    run_gradual_congestion()
