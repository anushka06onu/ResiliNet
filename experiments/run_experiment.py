#!/usr/bin/env python3

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def get_git_commit(project_root):
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"

def get_dependencies():
    try:
        res = subprocess.run(["python3", "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
        return res.stdout.strip().split("\n")
    except Exception:
        return []

def get_python_version():
    import sys
    return sys.version

import shutil
import sys

# Ensure network is accessible
project_root_dir = Path(__file__).resolve().parents[1]
if str(project_root_dir) not in sys.path:
    sys.path.append(str(project_root_dir))

from network.routing.policies import normalize_policy, get_scientific_label


EXIT_CODES = {
    "completed": 0,
    "fixture_generated": 0,
    "environment_unavailable": 2,
    "controller_failed": 3,
    "scenario_failed": 4,
    "timed_out": 5,
    "completed_with_missing_evidence": 6,
    "policy_sync_failed": 7,
    "cleanup_failed": 8,
    "backend_finalization_failed": 9
}

import re


def run_experiment(scenario, duration, seed, experiment_id=None, policy="predictive", allow_mock=False, results_root=None, overwrite=False, require_sync=False):
    effective_policy = normalize_policy(policy)
    scientific_policy = get_scientific_label(policy)

    if not experiment_id:
        experiment_id = f"{scenario}_{effective_policy}_seed{seed}"

    # Strict experiment ID validation to avoid any path injection or directory collisions
    if not re.fullmatch(r"[A-Za-z0-9_-]+", experiment_id):
        raise ValueError(f"Invalid experiment ID: '{experiment_id}'. Must match [A-Za-z0-9_-]+")

    print(f"Starting Mininet experiment: {experiment_id} (Requested Policy: {policy}, Canonical: {effective_policy}, Scientific: {scientific_policy})")

    # Resolve absolute paths based on this script's location
    project_root = Path(__file__).resolve().parents[1]
    base_results = Path(results_root) if results_root else project_root / "experiments" / "results"
    results_dir = (base_results / experiment_id).resolve()
    base_resolved = base_results.resolve()

    # Ensure path containment within base results directory
    if not (results_dir == base_resolved or base_resolved in results_dir.parents):
        raise ValueError(f"Target directory {results_dir} resolves outside base results directory {base_results}")

    if results_dir.exists() and mode_check_is_active(results_dir):
        if not overwrite:
            raise FileExistsError(f"Experiment directory {results_dir} already exists. Pass --overwrite to replace.")
        else:
            # Clean old run directory completely so stale artifacts are never mixed or hashed
            shutil.rmtree(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    status = "starting"
    start_time = datetime.now(timezone.utc).isoformat()

    has_ryu = shutil.which("ryu-manager") is not None
    mode = "REAL"

    # For live Mininet execution, synchronization with orchestrator is mandatory by default
    effective_require_sync = require_sync or (has_ryu and not allow_mock)
    internal_token = os.environ.get("RESILINET_INTERNAL_TOKEN", "resilinet-internal-secret-token")

    policy_sync_info = {
        "required": effective_require_sync,
        "attempted": False,
        "successful": False,
        "requested_policy": policy,
        "effective_policy": effective_policy,
        "scientific_policy": scientific_policy
    }

    finalization_info = {
        "required": effective_require_sync,
        "attempted": False,
        "successful": False,
        "artifacts": ["telemetry.csv", "predictions.csv", "routing_decisions.jsonl"]
    }

    if not has_ryu:
        if not allow_mock:
            print("ryu-manager not found. Mock mode not explicitly allowed.")
            status = "environment_unavailable"
            mode = "REAL"
        else:
            print("ryu-manager not found. Running in mock environment mode.")
            mode = "MOCK_TEST"
            status = "fixture_generated"
            time.sleep(1)

            # Generate realistic fixture rows for parsing pipeline verification
            with open(results_dir / "telemetry.csv", "w") as f:
                f.write("timestamp,experiment_id,switch_id,port_no,rx_bytes,tx_bytes,control_plane_rtt_ms,tx_dropped,loss_percent,utilization,data_origin\n")
                f.write(f"2026-01-01T00:00:00Z,{experiment_id},s1,1,10000,20000,10.5,0,0.1,0.2,mock\n")
                f.write(f"2026-01-01T00:00:02Z,{experiment_id},s1,1,25000,45000,11.2,0,0.1,0.3,mock\n")

            with open(results_dir / "predictions.csv", "w") as f:
                f.write("timestamp,link_id,congestion_probability,is_violation_predicted,data_origin\n")
                f.write("2026-01-01T00:00:02Z,s1-p1,0.15,False,mock\n")

            with open(results_dir / "routing_decisions.jsonl", "w") as f:
                f.write(json.dumps({
                    "decision_id": f"dec_{experiment_id}_1",
                    "experiment_id": experiment_id,
                    "flow_id": "f_1",
                    "timestamp": "2026-01-01T00:00:02Z",
                    "risk_before": 0.15,
                    "risk_after": 0.10,
                    "original_path": ["s1", "s2"],
                    "proposed_path": ["s1", "s3", "s2"],
                    "safeguard_result": "SAFEGUARD_PASSED",
                    "installation_status": "INSTALLED",
                    "verification_status": "VERIFIED",
                    "outcome_status": "SUCCESS",
                    "data_origin": "mock"
                }) + "\n")

            with open(results_dir / "controller.log", "w") as f:
                f.write(f"[INFO] Requested policy: {policy}\n[INFO] Effective policy: {effective_policy}\n[INFO] Policy implementation: PredictiveRouter:{effective_policy}\n")

            with open(results_dir / "scenario.log", "w") as f:
                f.write(f"[INFO] Mock Scenario {scenario} completed for {experiment_id}\n")
    else:
        # Try to synchronize with local Orchestrator if backend is running
        try:
            import urllib.request
            req_data = json.dumps({"policy": policy}).encode('utf-8')
            req = urllib.request.Request(
                f"http://localhost:8000/api/v1/internal/experiments/{experiment_id}/configure",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "X-ResiliNet-Internal-Token": internal_token
                }
            )
            policy_sync_info["attempted"] = True
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    res_json = json.loads(resp.read().decode())
                    if res_json.get("effective_policy") == effective_policy:
                        policy_sync_info["successful"] = True
                        print(f"Synchronized with Orchestrator: effective policy = {effective_policy}")
        except Exception as e:
            if effective_require_sync:
                print(f"Error: Required policy synchronization failed: {e}")
                status = "policy_sync_failed"

        if status != "policy_sync_failed":
            # 1. Start Ryu controller in background
            print("Starting Ryu controller...")
            ryu_script = project_root / "network" / "controller" / "resilinet_ryu.py"
            ryu_cmd = ["ryu-manager", str(ryu_script)]
            ryu_env = os.environ.copy()
            ryu_env["RESILINET_POLICY"] = effective_policy

            ryu_log = open(results_dir / "controller.log", "w")
            try:
                ryu_proc = subprocess.Popen(ryu_cmd, env=ryu_env, stdout=ryu_log, stderr=subprocess.STDOUT)
                time.sleep(3) # Wait for Ryu to start

                if ryu_proc.poll() is not None:
                    print("Ryu controller failed to start.")
                    status = "controller_failed"

                mn_proc = None
                if status == "starting":
                    # 2. Run the Mininet scenario script
                    print(f"Running Mininet script for {scenario} with policy {effective_policy}...")
                    scenario_path = project_root / "experiments" / "scenarios" / f"{scenario}.py"

                    if not scenario_path.exists():
                        print(f"Scenario {scenario_path} not found.")
                        status = "scenario_failed"
                    else:
                        mn_env = os.environ.copy()
                        mn_env["EXPERIMENT_SEED"] = str(seed)
                        mn_env["EXPERIMENT_DURATION"] = str(duration)
                        mn_env["EXPERIMENT_ID"] = experiment_id
                        mn_env["RESILINET_POLICY"] = effective_policy
                        mn_env["RESILINET_RESULTS_DIR"] = str(results_dir)

                        mn_log = open(results_dir / "scenario.log", "w")
                        try:
                            mn_proc = subprocess.Popen(["sudo", "python3", str(scenario_path)], env=mn_env, stdout=mn_log, stderr=subprocess.STDOUT)

                            # Wait for completion
                            try:
                                mn_ret = mn_proc.wait(timeout=duration + 10)
                                if mn_ret != 0:
                                    status = "scenario_failed"
                                else:
                                    status = "completed"
                            except subprocess.TimeoutExpired:
                                print("Experiment timed out. Cleaning up...")
                                mn_proc.send_signal(signal.SIGINT)
                                try:
                                    mn_proc.wait(timeout=10)
                                except subprocess.TimeoutExpired:
                                    mn_proc.kill()
                                status = "timed_out"
                        finally:
                            mn_log.close()
            finally:
                # 3. Clean up
                print("Cleaning up Mininet and Ryu...")
                cleanup_proc = subprocess.run(["sudo", "mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if cleanup_proc.returncode != 0 and status == "completed":
                    status = "cleanup_failed"

                if 'ryu_proc' in locals() and ryu_proc.poll() is None:
                    ryu_proc.terminate()
                    try:
                        ryu_proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        ryu_proc.kill()

                if not ryu_log.closed:
                    ryu_log.close()

    # If backend was synchronized and run succeeded, request backend record finalization into isolated directory
    if policy_sync_info.get("successful") and status in {"completed", "fixture_generated"}:
        finalization_info["attempted"] = True
        try:
            import urllib.request
            fin_req = urllib.request.Request(
                f"http://localhost:8000/api/v1/internal/experiments/{experiment_id}/finalize",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "X-ResiliNet-Internal-Token": internal_token
                }
            )
            with urllib.request.urlopen(fin_req, timeout=2) as resp:
                if resp.status == 200:
                    finalization_info["successful"] = True
                    print("Backend telemetry and decision records finalized to run directory.")
        except Exception as e:
            print(f"Notice: Finalization callback error: {e}")
            finalization_info["successful"] = False

        # Validate that required finalization artifacts are present
        has_tel = (results_dir / "telemetry.csv").exists()
        has_pred = (results_dir / "predictions.csv").exists()
        has_dec = (results_dir / "routing_decisions.jsonl").exists()
        if not (has_tel and has_pred and has_dec):
            if status == "completed":
                status = "backend_finalization_failed"

    # Check evidence report if present
    ev_report_path = results_dir / "evidence_report.json"
    evidence_complete = False
    if ev_report_path.exists():
        try:
            with open(ev_report_path, "r") as rf:
                ev_data = json.load(rf)
            before_ok = ev_data.get("stage_before", {}).get("complete", False)
            after_ok = ev_data.get("stage_after", {}).get("complete", False)
            evidence_complete = (before_ok and after_ok)
            if status == "completed" and not evidence_complete:
                status = "completed_with_missing_evidence"
        except Exception:
            evidence_complete = False

    end_time = datetime.now(timezone.utc).isoformat()

    # Save manifest
    executed_in_mininet = (mode == "REAL" and status not in {"environment_unavailable", "controller_failed", "scenario_failed", "policy_sync_failed", "backend_finalization_failed"})
    manifest = {
        "experiment_id": experiment_id,
        "scenario": scenario,
        "seed": seed,
        "duration": duration,
        "requested_policy": policy,
        "effective_policy": effective_policy,
        "scientific_policy": scientific_policy,
        "policy_implementation": f"PredictiveRouter:{effective_policy}",
        "policy_sync": policy_sync_info,
        "backend_finalization": finalization_info,
        "status": status,
        "mode": mode,
        "real_experiment": executed_in_mininet,
        "data_origin": "mininet" if executed_in_mininet else "mock",
        "evidence_scope": "network_experiment" if executed_in_mininet else "pipeline_testing",
        "predictive_performance_validated": False,
        "evidence_complete": evidence_complete if executed_in_mininet else True,
        "metadata": {
            "start_time": start_time,
            "end_time": end_time,
            "git_commit": get_git_commit(project_root),
            "python_version": get_python_version(),
            "dependencies": get_dependencies()
        }
    }

    with open(results_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Automatically generate SHA256SUMS for all generated artifacts in the isolated run directory
    try:
        import hashlib
        sums_file = results_dir / "SHA256SUMS"
        with open(sums_file, "w") as sf:
            for art in sorted(results_dir.rglob("*")):
                if art.is_file() and art != sums_file:
                    rel_path = art.relative_to(results_dir)
                    h = hashlib.sha256()
                    with open(art, "rb") as fl:
                        for chunk in iter(lambda: fl.read(65536), b""):
                            h.update(chunk)
                    sf.write(f"{h.hexdigest()}  {rel_path}\n")
    except Exception as e:
        print(f"Notice: Automated SHA256SUMS generation skipped: {e}")

    print(f"Experiment {experiment_id} finished with status: {status}")
    exit_code = EXIT_CODES.get(status, 1)
    return exit_code


def mode_check_is_active(d: Path) -> bool:
    """Helper to check if directory has existing contents."""
    return any(d.iterdir()) if d.exists() else False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ResiliNet Mininet Experiments")
    parser.add_argument("--scenario", type=str, required=True, choices=["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"])
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for traffic generation")
    parser.add_argument("--experiment-id", type=str, default=None, help="Experiment ID for tracking")
    parser.add_argument("--policy", type=str, default="predictive", choices=["static", "reactive", "predictive", "no_reroute", "reactive_threshold", "predictive_ml"], help="Routing policy to use")
    parser.add_argument("--allow-mock", action="store_true", help="Allow running mock experiment if Ryu/Mininet is unavailable")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing experiment result directory")
    parser.add_argument("--require-sync", action="store_true", help="Require successful backend policy synchronization before running")

    args = parser.parse_args()
    code = run_experiment(args.scenario, args.duration, args.seed, args.experiment_id, args.policy, args.allow_mock, overwrite=args.overwrite, require_sync=args.require_sync)
    if code != 0:
        sys.exit(code)
