#!/usr/bin/env python3

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path


def run_experiment(scenario, duration, seed, experiment_id=None):
    if not experiment_id:
        experiment_id = f"{scenario}_seed{seed}"
        
    print(f"Starting Mininet experiment: {experiment_id}")
    
    # Resolve absolute paths based on this script's location
    project_root = Path(__file__).resolve().parents[1]
    results_dir = project_root / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    status = "starting"
    
    # 1. Start Ryu controller in background
    print("Starting Ryu controller...")
    ryu_script = project_root / "network" / "controller" / "resilinet_ryu.py"
    ryu_cmd = ["ryu-manager", str(ryu_script)]
    
    ryu_log = open(results_dir / f"{experiment_id}_controller.log", "w")
    ryu_proc = subprocess.Popen(ryu_cmd, stdout=ryu_log, stderr=subprocess.STDOUT)
    time.sleep(3) # Wait for Ryu to start
    
    if ryu_proc.poll() is not None:
        print("Ryu controller failed to start.")
        status = "controller_failed"
        
    mn_proc = None
    if status == "starting":
        # 2. Run the Mininet scenario script
        print(f"Running Mininet script for {scenario}...")
        scenario_path = project_root / "experiments" / "scenarios" / f"{scenario}.py"
        
        if not scenario_path.exists():
            print(f"Scenario {scenario_path} not found.")
            status = "scenario_failed"
        else:
            mn_env = os.environ.copy()
            mn_env["EXPERIMENT_SEED"] = str(seed)
            mn_env["EXPERIMENT_DURATION"] = str(duration)
            mn_env["EXPERIMENT_ID"] = experiment_id
            
            mn_log = open(results_dir / f"{experiment_id}_scenario.log", "w")
            mn_proc = subprocess.Popen(["sudo", "python3", scenario_path], env=mn_env, stdout=mn_log, stderr=subprocess.STDOUT)
            
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
                mn_proc.wait()
                status = "timed_out"
            
            mn_log.close()
            
    # 3. Clean up
    print("Cleaning up Mininet and Ryu...")
    cleanup_proc = subprocess.run(["sudo", "mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if cleanup_proc.returncode != 0 and status == "completed":
        status = "cleanup_failed"
        
    ryu_proc.terminate()
    ryu_proc.wait()
    ryu_log.close()
    
    # Save manifest
    manifest = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "experiment_id": experiment_id,
        "scenario": scenario,
        "seed": seed,
        "duration": duration,
        "status": status
    }
    
    with open(results_dir / f"{experiment_id}_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Experiment {experiment_id} finished with status: {status}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ResiliNet Mininet Experiments")
    parser.add_argument("--scenario", type=str, required=True, choices=["normal", "gradual_congestion", "sudden_surge"])
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for traffic generation")
    parser.add_argument("--experiment-id", type=str, default=None, help="Experiment ID for tracking")
    
    args = parser.parse_args()
    run_experiment(args.scenario, args.duration, args.seed, args.experiment_id)
