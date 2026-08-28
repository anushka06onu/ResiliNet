#!/usr/bin/env python3
"""
ResiliNet Automated Campaign Orchestrator.

Executes complete experimental campaigns:
- Pilot: 1 Scenario (gradual_congestion) x 3 Policies x 2 Seeds (42, 43) = 6 Runs
- Full: 4 Scenarios x 3 Policies x 5 Seeds = 60 Runs
Generates campaign_manifest.json and triggers evaluation.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from experiments.evaluate_campaign import load_campaign_spec, evaluate_campaign
from experiments.artifact_validator import compute_campaign_invariant_fingerprint
from experiments.run_experiment import run_experiment


def run_campaign(is_pilot: bool = False, allow_mock: bool = True, duration_override: int = None):
    """Executes the campaign matrix and compiles campaign-level provenance."""
    spec = load_campaign_spec(project_root)
    campaign_id = f"campaign_{'pilot' if is_pilot else 'full'}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    if is_pilot:
        scenarios = [spec.get("pilot", {}).get("scenario", "gradual_congestion")]
        policies = spec.get("pilot", {}).get("policies", ["static", "reactive", "predictive"])
        seeds = spec.get("pilot", {}).get("seeds", [42, 43])
    else:
        scenarios = spec.get("scenarios", ["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"])
        policies = spec.get("policies", ["static", "reactive", "predictive"])
        seeds = spec.get("seeds", [42, 43, 44, 45, 46])

    duration = duration_override or spec.get("duration_seconds", 60)
    expected_combinations = [(sc, pol, sd) for sc in scenarios for pol in policies for sd in seeds]
    total_expected = len(expected_combinations)

    print(f"\n=======================================================")
    print(f"Starting ResiliNet Campaign: {campaign_id}")
    print(f"Mode: {'PILOT (6 Runs)' if is_pilot else 'FULL (60 Runs)'}")
    print(f"Expected Runs: {total_expected} ({len(scenarios)} scenarios x {len(policies)} policies x {len(seeds)} seeds)")
    print(f"=======================================================\n")

    start_time = datetime.now(timezone.utc).isoformat()
    invariant_fp = compute_campaign_invariant_fingerprint(project_root)

    run_results = []
    success_count = 0
    failure_count = 0

    results_root = project_root / "experiments" / "results"
    results_root.mkdir(parents=True, exist_ok=True)

    for idx, (scenario, policy, seed) in enumerate(expected_combinations, 1):
        exp_id = f"{scenario}_{policy}_seed{seed}"
        print(f"\n[{idx}/{total_expected}] Running {exp_id}...")

        ret = run_experiment(
            scenario=scenario,
            duration=duration,
            seed=seed,
            policy=policy,
            experiment_id=exp_id,
            allow_mock=allow_mock,
            results_root=results_root
        )

        status = "completed" if ret == 0 else "failed"
        if ret == 0:
            success_count += 1
        else:
            failure_count += 1

        run_results.append({
            "run_index": idx,
            "experiment_id": exp_id,
            "scenario": scenario,
            "policy": policy,
            "seed": seed,
            "exit_code": ret,
            "status": status
        })

    end_time = datetime.now(timezone.utc).isoformat()

    campaign_manifest = {
        "campaign_id": campaign_id,
        "mode": "pilot" if is_pilot else "full",
        "start_time": start_time,
        "end_time": end_time,
        "total_expected_runs": total_expected,
        "successful_runs": success_count,
        "failed_runs": failure_count,
        "campaign_invariant_fingerprint": invariant_fp["fingerprint"],
        "campaign_invariant_components": invariant_fp["components"],
        "run_log": run_results
    }

    manifest_path = results_root / "campaign_manifest.json"
    with open(manifest_path, "w") as mf:
        json.dump(campaign_manifest, mf, indent=2)

    print(f"\nCampaign execution finished: {success_count} succeeded, {failure_count} failed.")
    print(f"Campaign manifest saved to {manifest_path}")

    # Evaluate the completed campaign
    print("\nRunning statistical evaluation...")
    eval_result = evaluate_campaign(results_root, allow_incomplete=is_pilot)
    print(f"Evaluation complete. Matrix complete: {eval_result.get('matrix_complete')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ResiliNet Campaign Runner")
    parser.add_argument("--pilot", action="store_true", help="Run 6-run pilot campaign")
    parser.add_argument("--full", action="store_true", help="Run full 60-run campaign")
    parser.add_argument("--duration", type=int, default=None, help="Duration override in seconds")
    parser.add_argument("--no-mock", action="store_true", help="Refuse mock execution (require live Mininet)")
    args = parser.parse_args()

    is_pilot = args.pilot or (not args.full)
    run_campaign(is_pilot=is_pilot, allow_mock=(not args.no_mock), duration_override=args.duration)
