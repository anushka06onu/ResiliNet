#!/usr/bin/env python3
import json
import logging
import os
import subprocess
from pathlib import Path


def capture_switch_state(switches, results_dir, experiment_id, stage="before"):
    """
    Captures live OpenFlow flow tables and port statistics for active Mininet switches.
    stage: 'before' (baseline before congestion/intervention) or 'after' (post-reroute/congestion).
    """
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    capture_results = {
        "stage": stage,
        "switches_attempted": list(switches),
        "flow_dumps_captured": 0,
        "port_dumps_captured": 0,
        "captured_files": []
    }

    for sw in switches:
        # 1. Flow dump
        try:
            flow_res = subprocess.run(
                ["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", sw],
                capture_output=True, text=True, timeout=5
            )
            if flow_res.returncode == 0 and flow_res.stdout.strip():
                fname = f"{experiment_id}_{sw}_flows_{stage}.txt"
                with open(results_path / fname, "w") as f:
                    f.write(flow_res.stdout)
                capture_results["flow_dumps_captured"] += 1
                capture_results["captured_files"].append(fname)
        except Exception as e:
            logging.debug(f"Flow capture for {sw} at stage {stage} omitted: {e}")

        # 2. Port dump
        try:
            port_res = subprocess.run(
                ["ovs-ofctl", "-O", "OpenFlow13", "dump-ports", sw],
                capture_output=True, text=True, timeout=5
            )
            if port_res.returncode == 0 and port_res.stdout.strip():
                fname = f"{experiment_id}_{sw}_ports_{stage}.txt"
                with open(results_path / fname, "w") as f:
                    f.write(port_res.stdout)
                capture_results["port_dumps_captured"] += 1
                capture_results["captured_files"].append(fname)
        except Exception as e:
            logging.debug(f"Port capture for {sw} at stage {stage} omitted: {e}")

    return capture_results


def record_policy(policy, experiment_id, logger=None):
    """Verifies and logs the active routing policy for the experiment run."""
    valid_policies = ["static", "reactive", "predictive"]
    effective_policy = policy if policy in valid_policies else "predictive"
    msg = f"Active ResiliNet Routing Policy: {effective_policy} (Requested: {policy})"
    if logger:
        logger.info(msg)
    else:
        print(f"*** {msg}")
    return effective_policy
