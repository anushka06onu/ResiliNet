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

def run_experiment(scenario, duration, seed, experiment_id=None, policy="predictive", allow_mock=False):
    if not experiment_id:
        experiment_id = f"{scenario}_seed{seed}"

    print(f"Starting Mininet experiment: {experiment_id}")

    # Resolve absolute paths based on this script's location
    project_root = Path(__file__).resolve().parents[1]
    results_dir = project_root / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    status = "starting"
    start_time = datetime.now(timezone.utc).isoformat()

    import shutil
    has_ryu = shutil.which("ryu-manager") is not None
    mode = "REAL"

    if not has_ryu:
        if not allow_mock:
            print("ryu-manager not found. Mock mode not explicitly allowed.")
            status = "environment_unavailable"
            mode = "REAL"
        else:
            print("ryu-manager not found. Running in mock environment mode.")
            mode = "MOCK_TEST"
            status = "fixture_generated"
            results_dir = project_root / "experiments" / "results" / "mock"
            results_dir.mkdir(parents=True, exist_ok=True)
            time.sleep(1)

            # Generate realistic fixture rows for parsing pipeline verification
            with open(results_dir / f"{experiment_id}_telemetry.csv", "w") as f:
                f.write("timestamp,experiment_id,switch_id,port_no,rx_bytes,tx_bytes,control_plane_rtt_ms,tx_dropped,loss_percent,utilization\n")
                f.write(f"2026-01-01T00:00:00Z,{experiment_id},s1,1,10000,20000,10.5,0,0.1,0.2\n")
                f.write(f"2026-01-01T00:00:02Z,{experiment_id},s1,1,25000,45000,11.2,0,0.1,0.3\n")

            with open(results_dir / f"{experiment_id}_predictions.csv", "w") as f:
                f.write("timestamp,link_id,congestion_probability,is_violation_predicted\n")
                f.write("2026-01-01T00:00:02Z,s1-p1,0.15,False\n")

            with open(results_dir / f"{experiment_id}_routing_decisions.jsonl", "w") as f:
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
                    "outcome_status": "SUCCESS"
                }) + "\n")

            with open(results_dir / f"{experiment_id}_controller.log", "w") as f:
                f.write(f"[INFO] Mock Ryu Controller initialized for {experiment_id} with policy {policy}\n")

            with open(results_dir / f"{experiment_id}_scenario.log", "w") as f:
                f.write(f"[INFO] Mock Scenario {scenario} completed for {experiment_id}\n")
    else:
        # 1. Start Ryu controller in background
        print("Starting Ryu controller...")
        ryu_script = project_root / "network" / "controller" / "resilinet_ryu.py"
        ryu_cmd = ["ryu-manager", str(ryu_script)]
        ryu_env = os.environ.copy()
        ryu_env["RESILINET_POLICY"] = policy

        ryu_log = open(results_dir / f"{experiment_id}_controller.log", "w")
        try:
            ryu_proc = subprocess.Popen(ryu_cmd, env=ryu_env, stdout=ryu_log, stderr=subprocess.STDOUT)
            time.sleep(3) # Wait for Ryu to start

            if ryu_proc.poll() is not None:
                print("Ryu controller failed to start.")
                status = "controller_failed"

            mn_proc = None
            if status == "starting":
                # 2. Run the Mininet scenario script
                print(f"Running Mininet script for {scenario} with policy {policy}...")
                scenario_path = project_root / "experiments" / "scenarios" / f"{scenario}.py"

                if not scenario_path.exists():
                    print(f"Scenario {scenario_path} not found.")
                    status = "scenario_failed"
                else:
                    mn_env = os.environ.copy()
                    mn_env["EXPERIMENT_SEED"] = str(seed)
                    mn_env["EXPERIMENT_DURATION"] = str(duration)
                    mn_env["EXPERIMENT_ID"] = experiment_id
                    mn_env["RESILINET_POLICY"] = policy

                    mn_log = open(results_dir / f"{experiment_id}_scenario.log", "w")
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

    end_time = datetime.now(timezone.utc).isoformat()

    # Save manifest
    is_real = (mode == "REAL" and status == "completed")
    manifest = {
        "experiment_id": experiment_id,
        "scenario": scenario,
        "seed": seed,
        "duration": duration,
        "policy": policy,
        "status": status,
        "mode": mode,
        "real_experiment": is_real,
        "data_origin": "mininet" if is_real else "mock",
        "evidence_scope": "network_experiment" if is_real else "pipeline_testing",
        "predictive_performance_validated": False,
        "metadata": {
            "start_time": start_time,
            "end_time": end_time,
            "git_commit": get_git_commit(project_root),
            "python_version": get_python_version(),
            "dependencies": get_dependencies()
        }
    }

    with open(results_dir / f"{experiment_id}_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Automatically generate SHA256SUMS for all generated artifacts
    try:
        import hashlib
        sums_file = results_dir / f"{experiment_id}_SHA256SUMS"
        with open(sums_file, "w") as sf:
            for art in sorted(results_dir.glob(f"{experiment_id}_*")):
                if art == sums_file:
                    continue
                h = hashlib.sha256()
                with open(art, "rb") as fl:
                    for chunk in iter(lambda: fl.read(65536), b""):
                        h.update(chunk)
                sf.write(f"{h.hexdigest()}  {art.name}\n")
    except Exception as e:
        print(f"Notice: Automated SHA256SUMS generation skipped: {e}")

    print(f"Experiment {experiment_id} finished with status: {status}")
    if status == "environment_unavailable":
        import sys
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ResiliNet Mininet Experiments")
    parser.add_argument("--scenario", type=str, required=True, choices=["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"])
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for traffic generation")
    parser.add_argument("--experiment-id", type=str, default=None, help="Experiment ID for tracking")
    parser.add_argument("--policy", type=str, default="predictive", choices=["static", "reactive", "predictive"], help="Routing policy to use")
    parser.add_argument("--allow-mock", action="store_true", help="Allow running mock experiment if Ryu/Mininet is unavailable")

    args = parser.parse_args()
    run_experiment(args.scenario, args.duration, args.seed, args.experiment_id, args.policy, args.allow_mock)
