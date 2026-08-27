#!/usr/bin/env python3

import argparse
import subprocess
import time
import json
import os
import signal
from datetime import datetime

def run_experiment(scenario, duration, seed):
    print(f"Starting Mininet experiment: {scenario} (Seed: {seed})")
    
    # 1. Start Ryu controller in background
    print("Starting Ryu controller...")
    ryu_cmd = ["ryu-manager", "network/controller/simple_switch_13.py", "network/controller/rest_topology.py"]
    ryu_proc = subprocess.Popen(ryu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3) # Wait for Ryu to start
    
    # 2. Run the Mininet scenario script
    print(f"Running Mininet script for {scenario}...")
    scenario_path = f"experiments/scenarios/{scenario}.py"
    
    if not os.path.exists(scenario_path):
        print(f"Scenario {scenario_path} not found.")
        ryu_proc.terminate()
        return
        
    mn_env = os.environ.copy()
    mn_env["EXPERIMENT_SEED"] = str(seed)
    mn_env["EXPERIMENT_DURATION"] = str(duration)
    
    mn_proc = subprocess.Popen(["sudo", "python3", scenario_path], env=mn_env)
    
    # Wait for completion
    try:
        mn_proc.wait(timeout=duration + 10)
    except subprocess.TimeoutExpired:
        print("Experiment timed out. Cleaning up...")
        mn_proc.send_signal(signal.SIGINT)
        mn_proc.wait()
        
    # 3. Clean up
    print("Cleaning up Mininet and Ryu...")
    subprocess.run(["sudo", "mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ryu_proc.terminate()
    ryu_proc.wait()
    
    # Save manifest
    os.makedirs('experiments/results', exist_ok=True)
    manifest = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "scenario": scenario,
        "seed": seed,
        "duration": duration,
        "status": "completed"
    }
    
    with open(f"experiments/results/{scenario}_seed{seed}.json", "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Experiment {scenario} (Seed {seed}) finished successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ResiliNet Mininet Experiments")
    parser.add_argument("--scenario", type=str, required=True, choices=["normal", "gradual_congestion", "sudden_surge"])
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for traffic generation")
    
    args = parser.parse_args()
    run_experiment(args.scenario, args.duration, args.seed)
