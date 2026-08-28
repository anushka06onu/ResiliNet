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


def log_experiment_event(results_dir, event_type: str, details: dict = None, flow_id: str = None, link_id: str = None, episode_id: str = None):
    """Appends a structured timestamped event to scenario_events.jsonl in the run directory."""
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    exp_id = results_path.name
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "experiment_id": exp_id,
        "episode_id": episode_id or "ep_scenario",
        "flow_id": flow_id,
        "link_id": link_id,
        "source": "scenario",
        "details": details or {}
    }
    with open(results_path / "scenario_events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")
    return event


def merge_and_sort_events(results_dir: Path) -> int:
    """
    Merges scenario_events.jsonl and orchestrator_events.jsonl into a unified events.jsonl
    sorted strictly in chronological timestamp order.
    """
    results_path = Path(results_dir)
    all_events = []

    for src_name in ["scenario_events.jsonl", "orchestrator_events.jsonl", "events.jsonl"]:
        ev_file = results_path / src_name
        if ev_file.exists() and ev_file.name != "events.jsonl":
            for line in ev_file.read_text().splitlines():
                if line.strip():
                    try:
                        all_events.append(json.loads(line))
                    except Exception:
                        pass

    if all_events:
        all_events.sort(key=lambda x: x.get("timestamp", ""))
        with open(results_path / "events.jsonl", "w") as f:
            for ev in all_events:
                f.write(json.dumps(ev) + "\n")

    return len(all_events)


def apply_and_verify_netem(node, interface: str, delay_ms: float, loss_pct: float, results_dir, event_name="congestion_injected_at", stage=1):
    """Applies traffic control impairment and verifies actual activation in the Linux kernel."""
    import re
    cmd = f"tc qdisc change dev {interface} root netem delay {delay_ms}ms loss {loss_pct}%"
    out = node.cmd(cmd)
    show_out = node.cmd(f"tc qdisc show dev {interface}")

    observed_delay_ms = None
    observed_loss_pct = None

    match_delay = re.search(r"delay ([\d\.]+)ms", show_out)
    if match_delay:
        observed_delay_ms = float(match_delay.group(1))

    match_loss = re.search(r"loss ([\d\.]+)%", show_out)
    if match_loss:
        observed_loss_pct = float(match_loss.group(1))

    delay_matches = (observed_delay_ms is not None and abs(observed_delay_ms - delay_ms) < 0.5)
    loss_matches = (observed_loss_pct is not None and abs(observed_loss_pct - loss_pct) < 0.5)
    verified = ("netem" in show_out) and (out.strip() == "" or "error" not in out.lower()) and delay_matches and loss_matches

    details = {
        "command": cmd,
        "interface": interface,
        "requested_delay_ms": delay_ms,
        "observed_delay_ms": observed_delay_ms,
        "requested_loss_pct": loss_pct,
        "observed_loss_pct": observed_loss_pct,
        "cmd_output": out.strip(),
        "show_output": show_out.strip(),
        "verified": verified,
        "stage": stage
    }
    if verified:
        log_experiment_event(results_dir, event_name, details)
        return True
    else:
        log_experiment_event(results_dir, "congestion_injection_failed", details)
        raise RuntimeError(f"tc qdisc impairment verification failed on {interface}: req_delay={delay_ms}, obs_delay={observed_delay_ms}, req_loss={loss_pct}, obs_loss={observed_loss_pct} | output: {show_out}")


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
    try:
        from network.routing.policies import normalize_policy, get_scientific_label
        effective_policy = normalize_policy(policy)
        sci_label = get_scientific_label(policy)
    except Exception:
        effective_policy = policy
        sci_label = policy
    msg = f"Active ResiliNet Routing Policy: {effective_policy} [scientific: {sci_label}] (Requested: {policy})"
    if logger:
        logger.info(msg)
    else:
        print(f"*** {msg}")
    return effective_policy
