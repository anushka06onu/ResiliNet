#!/usr/bin/env python3
import time
import requests
import sys
import glob

API_URL = "http://localhost:8000/api/v1/experiments"

def run_smoke_test():
    print("Starting ResiliNet Smoke Test...")
    exp_id = "smoke_test_001"
    
    # 1. Start Experiment
    print(f"-> Starting experiment: {exp_id} (gradual_congestion)")
    res = requests.post(f"{API_URL}/{exp_id}/start", json={"scenario": "gradual_congestion", "duration": 60})
    if res.status_code != 200:
        print(f"Failed to start experiment: {res.text}")
        sys.exit(1)
        
    print("-> Waiting for experiment to finish (approx 70s)...")
    
    # Wait loop
    status = "running"
    while status == "running":
        time.sleep(5)
        res = requests.get(f"{API_URL}/{exp_id}")
        if res.status_code == 200:
            status = res.json().get("status")
        else:
            print("Failed to poll status")
            break
            
    print(f"-> Experiment finished with status: {status}")
    
    # Stop explicitly to flush artifacts
    print("-> Stopping experiment to flush artifacts...")
    requests.post(f"{API_URL}/{exp_id}/stop")
    
    # Verify Artifacts
    print("-> Verifying artifacts...")
    artifacts = [
        f"{exp_id}_manifest.json",
        f"{exp_id}_telemetry.csv",
        f"{exp_id}_predictions.csv",
        f"{exp_id}_routing_decisions.jsonl",
        f"{exp_id}_controller.log",
        f"{exp_id}_scenario.log"
    ]
    
    missing = []
    for art in artifacts:
        if not glob.glob(f"experiments/results/{art}"):
            missing.append(art)
            
    if missing:
        print(f"-> FAILED: Missing artifacts: {missing}")
    else:
        print("-> SUCCESS: All artifacts generated!")

if __name__ == "__main__":
    run_smoke_test()
