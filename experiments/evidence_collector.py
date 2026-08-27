#!/usr/bin/env python3
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def log_experiment_event(results_dir, event_type: str, details: dict = None):
    """Appends a structured timestamped event to events.jsonl in the run directory."""
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "details": details or {}
    }
    with open(results_path / "events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")
    return event


def capture_switch_state(switches, results_dir, stage="before", experiment_id=None):
    """
    Captures live OpenFlow flow tables and port statistics for active Mininet switches.
    Records structured command provenance including byte counts, return codes, and SHA-256 digests.
    stage: 'before' (baseline before congestion/intervention) or 'after' (post-reroute/congestion).
    """
    results_path = Path(results_dir)
    switches_dir = results_path / "switches"
    switches_dir.mkdir(parents=True, exist_ok=True)

    capture_results = {
        "stage": stage,
        "switches_attempted": list(switches),
        "flow_dumps_captured": 0,
        "port_dumps_captured": 0,
        "complete": False,
        "command_provenance": []
    }

    for sw in switches:
        # 1. Flow dump
        flow_cmd = ["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", sw]
        captured_at = datetime.now(timezone.utc).isoformat()
        try:
            flow_res = subprocess.run(flow_cmd, capture_output=True, text=True, timeout=5)
            fname = f"{sw}_flows_{stage}.txt"
            target_path = switches_dir / fname

            if flow_res.returncode == 0 and flow_res.stdout.strip():
                with open(target_path, "w") as f:
                    f.write(flow_res.stdout)
                capture_results["flow_dumps_captured"] += 1
                raw_bytes = flow_res.stdout.encode('utf-8')
                capture_results["command_provenance"].append({
                    "command": " ".join(flow_cmd),
                    "return_code": flow_res.returncode,
                    "captured_at": captured_at,
                    "switch": sw,
                    "type": "flow_dump",
                    "stage": stage,
                    "file": f"switches/{fname}",
                    "byte_count": len(raw_bytes),
                    "sha256": sha256_bytes(raw_bytes)
                })
            else:
                capture_results["command_provenance"].append({
                    "command": " ".join(flow_cmd),
                    "return_code": flow_res.returncode,
                    "captured_at": captured_at,
                    "switch": sw,
                    "type": "flow_dump",
                    "stage": stage,
                    "error": flow_res.stderr.strip() if flow_res.stderr else "Empty output"
                })
        except Exception as e:
            logging.debug(f"Flow capture for {sw} at stage {stage} omitted: {e}")
            capture_results["command_provenance"].append({
                "command": " ".join(flow_cmd),
                "return_code": -1,
                "captured_at": captured_at,
                "switch": sw,
                "type": "flow_dump",
                "stage": stage,
                "error": str(e)
            })

        # 2. Port dump
        port_cmd = ["ovs-ofctl", "-O", "OpenFlow13", "dump-ports", sw]
        captured_at = datetime.now(timezone.utc).isoformat()
        try:
            port_res = subprocess.run(port_cmd, capture_output=True, text=True, timeout=5)
            fname = f"{sw}_ports_{stage}.txt"
            target_path = switches_dir / fname

            if port_res.returncode == 0 and port_res.stdout.strip():
                with open(target_path, "w") as f:
                    f.write(port_res.stdout)
                capture_results["port_dumps_captured"] += 1
                raw_bytes = port_res.stdout.encode('utf-8')
                capture_results["command_provenance"].append({
                    "command": " ".join(port_cmd),
                    "return_code": port_res.returncode,
                    "captured_at": captured_at,
                    "switch": sw,
                    "type": "port_dump",
                    "stage": stage,
                    "file": f"switches/{fname}",
                    "byte_count": len(raw_bytes),
                    "sha256": sha256_bytes(raw_bytes)
                })
            else:
                capture_results["command_provenance"].append({
                    "command": " ".join(port_cmd),
                    "return_code": port_res.returncode,
                    "captured_at": captured_at,
                    "switch": sw,
                    "type": "port_dump",
                    "stage": stage,
                    "error": port_res.stderr.strip() if port_res.stderr else "Empty output"
                })
        except Exception as e:
            logging.debug(f"Port capture for {sw} at stage {stage} omitted: {e}")
            capture_results["command_provenance"].append({
                "command": " ".join(port_cmd),
                "return_code": -1,
                "captured_at": captured_at,
                "switch": sw,
                "type": "port_dump",
                "stage": stage,
                "error": str(e)
            })

    total_expected = len(switches)
    capture_results["complete"] = (
        capture_results["flow_dumps_captured"] == total_expected and
        capture_results["port_dumps_captured"] == total_expected
    )

    # Append to cumulative evidence_report.json
    report_path = results_path / "evidence_report.json"
    try:
        report = {}
        if report_path.exists():
            with open(report_path, "r") as rf:
                report = json.load(rf)
        report[f"stage_{stage}"] = capture_results
        with open(report_path, "w") as wf:
            json.dump(report, wf, indent=2)
    except Exception as e:
        logging.debug(f"Failed to update evidence_report.json: {e}")

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
