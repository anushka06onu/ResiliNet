#!/usr/bin/env python3
"""
ResiliNet Automated Campaign Orchestrator.

Executes complete experimental campaigns:
- Pilot: 1 Scenario (gradual_congestion) x 3 Policies x 2 Seeds (42, 43) = 6 Runs
- Full: 4 Scenarios x 3 Policies x 5 Seeds = 60 Runs
Default: Real Mininet required (allow_mock=False).
Safely continues after exceptions and saves campaign manifest progress after every run.
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


def run_campaign(is_pilot: bool = False, allow_mock: bool = False, duration_override: int = None, overwrite: bool = False):
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
    print(f"Execution: {'MOCK ALLOWED' if allow_mock else 'REAL MININET MANDATORY'}")
    print(f"Expected Runs: {total_expected} ({len(scenarios)} scenarios x {len(policies)} policies x {len(seeds)} seeds)")
    print(f"=======================================================\n")

    start_time = datetime.now(timezone.utc).isoformat()
    invariant_fp = compute_campaign_invariant_fingerprint(project_root)

    run_results = []
    completed_eligible_runs = 0
    mock_fixture_runs = 0
    failed_runs = 0
    excluded_runs = 0
    already_completed_runs = 0

    results_root = project_root / "experiments" / "results"
    results_root.mkdir(parents=True, exist_ok=True)
    manifest_path = results_root / "campaign_manifest.json"

    def save_campaign_progress():
        """Persists campaign manifest state after every run iteration."""
        progress_data = {
            "campaign_id": campaign_id,
            "mode": "pilot" if is_pilot else "full",
            "execution_mode": "mock_allowed" if allow_mock else "real_mininet",
            "start_time": start_time,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_expected_runs": total_expected,
            "completed_eligible_runs": completed_eligible_runs,
            "mock_fixture_runs": mock_fixture_runs,
            "failed_runs": failed_runs,
            "excluded_runs": excluded_runs,
            "already_completed_runs": already_completed_runs,
            "campaign_invariant_fingerprint": invariant_fp["fingerprint"],
            "campaign_invariant_components": invariant_fp["components"],
            "run_log": run_results
        }
        with open(manifest_path, "w") as mf:
            json.dump(progress_data, mf, indent=2)

    for idx, (scenario, policy, seed) in enumerate(expected_combinations, 1):
        exp_id = f"{scenario}_{policy}_seed{seed}"
        exp_dir = results_root / exp_id
        manifest_file = exp_dir / "manifest.json"

        # Check for already completed eligible run
        if not overwrite and manifest_file.exists():
            try:
                mdata = json.loads(manifest_file.read_text())
                if (mdata.get("status") == "completed" and
                    mdata.get("real_experiment") is True and
                    mdata.get("eligible_for_analysis") is True and
                    mdata.get("data_origin") == "mininet"):
                    print(f"\n[{idx}/{total_expected}] Skipping already completed eligible run: {exp_id}")
                    already_completed_runs += 1
                    completed_eligible_runs += 1
                    run_results.append({
                        "run_index": idx,
                        "experiment_id": exp_id,
                        "scenario": scenario,
                        "policy": policy,
                        "seed": seed,
                        "status": "already_completed",
                        "eligible_for_analysis": True,
                        "data_origin": "mininet"
                    })
                    save_campaign_progress()
                    continue
            except Exception:
                pass

        print(f"\n[{idx}/{total_expected}] Running {exp_id}...")

        try:
            ret = run_experiment(
                scenario=scenario,
                duration=duration,
                seed=seed,
                policy=policy,
                experiment_id=exp_id,
                allow_mock=allow_mock,
                results_root=results_root,
                overwrite=True
            )

            # Read actual generated manifest to determine true scientific eligibility
            m_status = "unknown"
            is_eligible = False
            is_real = False
            origin = "unknown"

            if manifest_file.exists():
                try:
                    mdata = json.loads(manifest_file.read_text())
                    m_status = mdata.get("status", "unknown")
                    is_real = mdata.get("real_experiment", False)
                    is_eligible = mdata.get("eligible_for_analysis", False)
                    origin = mdata.get("data_origin", "unknown")
                except Exception:
                    pass

            if is_eligible and is_real and origin == "mininet" and m_status == "completed":
                completed_eligible_runs += 1
            elif origin == "mock" or m_status == "fixture_generated":
                mock_fixture_runs += 1
                excluded_runs += 1
            else:
                failed_runs += 1
                excluded_runs += 1

            run_results.append({
                "run_index": idx,
                "experiment_id": exp_id,
                "scenario": scenario,
                "policy": policy,
                "seed": seed,
                "exit_code": ret,
                "status": m_status,
                "eligible_for_analysis": is_eligible,
                "data_origin": origin
            })

        except Exception as exc:
            print(f"Error executing run {exp_id}: {exc}")
            failed_runs += 1
            excluded_runs += 1
            run_results.append({
                "run_index": idx,
                "experiment_id": exp_id,
                "scenario": scenario,
                "policy": policy,
                "seed": seed,
                "exit_code": -1,
                "status": "exception",
                "error": str(exc),
                "eligible_for_analysis": False,
                "data_origin": "failed"
            })

        save_campaign_progress()

    print(f"\n=======================================================")
    print(f"Campaign execution finished.")
    print(f"Eligible Mininet runs: {completed_eligible_runs}/{total_expected}")
    print(f"Mock/Fixture runs: {mock_fixture_runs}")
    print(f"Failed runs: {failed_runs}")
    print(f"Manifest written to: {manifest_path}")
    print(f"=======================================================\n")

    # Evaluate the completed campaign
    print("Running campaign evaluation...")
    eval_result = evaluate_campaign(results_root, allow_incomplete=(is_pilot or completed_eligible_runs < total_expected))
    print(f"Evaluation complete. Matrix complete: {eval_result.get('matrix_complete')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ResiliNet Campaign Runner")
    parser.add_argument("--pilot", action="store_true", help="Run 6-run pilot campaign")
    parser.add_argument("--full", action="store_true", help="Run full 60-run campaign")
    parser.add_argument("--allow-mock", action="store_true", help="Allow mock execution (pipeline testing only)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing completed runs")
    parser.add_argument("--duration", type=int, default=None, help="Duration override in seconds")
    args = parser.parse_args()

    is_pilot = args.pilot or (not args.full)
    run_campaign(
        is_pilot=is_pilot,
        allow_mock=args.allow_mock,
        duration_override=args.duration,
        overwrite=args.overwrite
    )
