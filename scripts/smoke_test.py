#!/usr/bin/env python3
import glob
import subprocess
import sys
import time
from pathlib import Path

import httpx

API_URL = "http://localhost:8000/api/v1/experiments"

def wait_for_backend(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            res = httpx.get("http://localhost:8000/api/v1/topology/current", timeout=2)
            if res.status_code == 200:
                return True
        except httpx.RequestError:
            time.sleep(2)
    return False

def run_smoke_test():
    print("Starting ResiliNet Smoke Test...")
    exp_id = "smoke_test_001"

    # 1. Start Backend
    print("-> Starting backend uvicorn server...")
    backend_proc = subprocess.Popen(["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"], cwd="backend")

    try:
        if not wait_for_backend():
            print("Failed to start backend within timeout.")
            sys.exit(1)

        # 2. Start Experiment
        print(f"-> Starting experiment: {exp_id} (gradual_congestion)")
        res = httpx.post(f"{API_URL}/{exp_id}/start", json={"scenario": "gradual_congestion", "duration": 60, "policy": "predictive", "seed": 42}, timeout=10)
        if res.status_code != 200:
            print(f"Failed to start experiment: {res.text}")
            sys.exit(1)

        print("-> Waiting for experiment to finish (approx 70s)...")

        # Wait loop
        status = "running"
        while status == "running":
            time.sleep(5)
            try:
                res = httpx.get(f"{API_URL}/{exp_id}", timeout=5)
                if res.status_code == 200:
                    status = res.json().get("status")
                else:
                    print("Failed to poll status")
                    break
            except httpx.RequestError as e:
                print(f"Error polling status: {e}")
                break

        print(f"-> Experiment finished with status: {status}")

        # Stop explicitly to flush artifacts
        print("-> Stopping experiment to flush artifacts...")
        try:
            httpx.post(f"{API_URL}/{exp_id}/stop", timeout=5)
        except httpx.RequestError as e:
            print(f"-> Warning: Stop endpoint request failed: {e}")

        # Verify Artifacts
        print("-> Verifying artifacts strictly...")
        import os
        import json
        artifacts = [
            f"{exp_id}_manifest.json",
            f"{exp_id}_telemetry.csv",
            f"{exp_id}_predictions.csv",
            f"{exp_id}_routing_decisions.jsonl",
            f"{exp_id}_controller.log",
            f"{exp_id}_scenario.log"
        ]

        for art in artifacts:
            path = Path("experiments/results") / art
            if not path.exists():
                print(f"-> FAILED: Missing artifact: {art}")
                sys.exit(1)
            if path.stat().st_size == 0:
                print(f"-> FAILED: {art} is empty")
                sys.exit(1)

        # Validate manifest
        manifest_path = Path("experiments/results") / f"{exp_id}_manifest.json"
        with manifest_path.open("r") as f:
            manifest = json.load(f)
        if manifest.get("mode") != "REAL":
            print(f"-> FAILED: Experiment mode is {manifest.get('mode')}, expected REAL. Mock artifacts are rejected.")
            sys.exit(1)
        if manifest.get("status") != "completed":
            print(f"-> FAILED: Experiment status is {manifest.get('status')}, expected completed.")
            sys.exit(1)

        # Validate row counts
        with open(Path("experiments/results") / f"{exp_id}_telemetry.csv") as f:
            if sum(1 for _ in f) < 3:
                print("-> FAILED: Telemetry file has insufficient rows.")
                sys.exit(1)
        with open(Path("experiments/results") / f"{exp_id}_predictions.csv") as f:
            if sum(1 for _ in f) < 3:
                print("-> FAILED: Predictions file has insufficient rows.")
                sys.exit(1)

        print("-> SUCCESS: All artifacts generated and strictly validated!")
    finally:
        print("-> Shutting down backend server...")
        backend_proc.terminate()
        try:
            backend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_proc.kill()

        print("-> Cleaning up Mininet (mn -c)...")
        subprocess.run(["sudo", "mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    run_smoke_test()
