#!/usr/bin/env python3
import time
import requests
import sys

API_URL = "http://localhost:8000/api/v1/experiments"
POLICIES = ["static", "reactive", "predictive"]
SCENARIOS = ["normal", "gradual_congestion", "sudden_surge"]
SEEDS = [42, 100, 200]
DURATION = 60

def run_experiment(policy, scenario, seed):
    exp_id = f"exp_{policy}_{scenario}_seed{seed}"
    print(f"-> Starting {exp_id}...")
    
    config = {
        "scenario": scenario,
        "duration": DURATION,
        "seed": seed,
        "policy": policy
    }
    
    res = requests.post(f"{API_URL}/{exp_id}/start", json=config)
    if res.status_code != 200:
        print(f"Failed to start experiment {exp_id}: {res.text}")
        return False
        
    print(f"   Waiting for {DURATION + 10} seconds...")
    status = "running"
    while status == "running":
        time.sleep(5)
        try:
            res = requests.get(f"{API_URL}/{exp_id}")
            if res.status_code == 200:
                status = res.json().get("status")
            else:
                print("   Failed to poll status")
                break
        except requests.exceptions.RequestException:
            pass

    print(f"   Stopping {exp_id} to flush artifacts...")
    requests.post(f"{API_URL}/{exp_id}/stop")
    return True

if __name__ == "__main__":
    print(f"Starting batch run of {len(POLICIES) * len(SCENARIOS) * len(SEEDS)} experiments")
    for policy in POLICIES:
        for scenario in SCENARIOS:
            for seed in SEEDS:
                run_experiment(policy, scenario, seed)
    print("Batch run complete!")
