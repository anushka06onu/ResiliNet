#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.append(project_root)
from datetime import timedelta

from data_pipeline.feature_engineering import FeaturePipeline
from data_pipeline.label_generation import generate_future_labels
from data_pipeline.validate_dataset import validate_feature_dataset
from ml.schema import CURRENT_FEATURE_SCHEMA_VERSION, MODEL_FEATURES


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_git_info() -> tuple[str, bool]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        commit = "unknown"

    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True
        ).strip()
        dirty = bool(status)
    except Exception:
        dirty = False

    return commit, dirty


def generate_mock_experiments():
    """
    Generate a highly realistic mock dataset with explicit experiment IDs.
    NOTE: All metrics are based on synthetic demonstration data and must not
    be interpreted as real-network performance.
    """
    print("WARNING: Generating synthetic demonstration dataset. Do not interpret as real network performance.")
    np.random.seed(42)
    experiments = [f"exp_{str(i).zfill(3)}" for i in range(1, 101)]

    rows = []
    for exp in experiments:
        num_samples = np.random.randint(50, 150)
        # Induce congestion in ~30% of experiments
        is_congested_exp = np.random.rand() < 0.3
        congestion_start = np.random.randint(20, num_samples - 20) if (is_congested_exp and num_samples > 40) else num_samples + 1

        pipeline = FeaturePipeline()
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rx_bytes_counter = 0
        tx_bytes_counter = 0
        tx_dropped_counter = 0

        for t in range(num_samples):
            current_time = base_time + timedelta(seconds=t * 2)

            congested = (t >= congestion_start)

            loss_percent = np.random.exponential(2.5) if congested else np.random.exponential(0.1)
            # Cumulative drop counter
            tx_dropped_counter += int(np.random.poisson(5) if congested else 0)
            latency = np.random.normal(15, 5) if congested else np.random.normal(3, 1)
            latency = max(0.5, latency) # Plausible positive RTT
            utilization = np.random.uniform(0.8, 1.0) if congested else np.random.uniform(0.1, 0.4)

            # Strictly non-negative byte increments
            rx_bytes_counter += max(10, int(np.random.normal(100, 30)))
            tx_bytes_counter += max(500, int(np.random.uniform(5000, 15000)) * 2)

            raw_metrics = {
                "loss_percent": loss_percent,
                "tx_dropped": tx_dropped_counter,
                "control_plane_rtt_ms": latency,
                "utilization": utilization,
                "rx_bytes": rx_bytes_counter,
                "tx_bytes": tx_bytes_counter
            }

            computed_features = pipeline.process_raw_telemetry(f"link_{exp}", raw_metrics, current_time)

            # Exclude warm-up rows (where status is INSUFFICIENT_DATA)
            if computed_features.get("status") == "OK":
                rows.append({
                    'experiment_id': exp,
                    'timestamp': t,
                    'src_switch': 's1',
                    'dst_switch': 's2',
                    'loss_mean_30s': computed_features['loss_mean_30s'],
                    'tx_dropped_max': computed_features['tx_dropped_max'],
                    'control_plane_rtt_ms': computed_features['control_plane_rtt_ms'],
                    'rx_bytes_slope': computed_features['rx_bytes_slope'],
                    'tx_bytes_rate': computed_features['tx_bytes_rate'],
                    'data_origin': 'synthetic',
                    'current_sla_violated': 1 if (computed_features['loss_mean_30s'] > 2.0 or computed_features['control_plane_rtt_ms'] > 20.0) else 0
                })

    df = pd.DataFrame(rows)

    # Use version-stable transform-based future label generation
    df = generate_future_labels(df, group_col='experiment_id', target_col='current_sla_violated', horizon_steps=15)
    df = df.dropna(subset=['sla_violated_in_horizon'])
    df['sla_violated_in_horizon'] = df['sla_violated_in_horizon'].astype(int)

    os.makedirs('data_pipeline/data', exist_ok=True)
    df.to_csv('data_pipeline/data/features_with_experiments.csv', index=False)
    return df


def strict_experiment_split(df):
    unique_exps = df['experiment_id'].unique()
    np.random.shuffle(unique_exps)

    n_total = len(unique_exps)
    train_idx = int(n_total * 0.6)
    val_idx = int(n_total * 0.8)

    train_exps = set(unique_exps[:train_idx])
    val_exps = set(unique_exps[train_idx:val_idx])
    test_exps = set(unique_exps[val_idx:])

    train_df = df[df['experiment_id'].isin(train_exps)]
    val_df = df[df['experiment_id'].isin(val_exps)]
    test_df = df[df['experiment_id'].isin(test_exps)]

    print(f"Dataset split by Complete Experiments. Total: {n_total}")
    print(f"Train Experiments: {len(train_exps)} | Val Experiments: {len(val_exps)} | Test Experiments: {len(test_exps)}")
    print(f"Train samples: {len(train_df)} | Val samples: {len(val_df)} | Test samples: {len(test_df)}")

    return train_df, val_df, test_df, test_exps


def evaluate_model(name, y_true, y_probs, threshold=0.5):
    y_pred = (y_probs > threshold).astype(int)

    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    roc = roc_auc_score(y_true, y_probs)
    pr_auc = average_precision_score(y_true, y_probs)
    brier = brier_score_loss(y_true, y_probs)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return {
        'threshold': float(threshold),
        'accuracy': float(acc),
        'precision': float(prec),
        'recall': float(rec),
        'f1': float(f1),
        'roc_auc': float(roc),
        'pr_auc': float(pr_auc),
        'brier_score': float(brier),
        'fpr': float(fpr),
        'confusion_matrix': {
            'tn': int(tn),
            'fp': int(fp),
            'fn': int(fn),
            'tp': int(tp)
        }
    }


def find_best_threshold(y_val, val_probs):
    thresholds = np.linspace(0.1, 0.9, 81)
    best_f1 = -1
    best_t = 0.5
    for t in thresholds:
        preds = (val_probs > t).astype(int)
        score = f1_score(y_val, preds, zero_division=0)
        if score > best_f1:
            best_f1 = score
            best_t = t
    return best_t


def run_baselines(X_train, y_train, X_test, y_test):
    results = {}

    # Baseline 1: Static Threshold
    dummy_probs = np.where((X_test['loss_mean_30s'] > 2.0) | (X_test['control_plane_rtt_ms'] > 20.0), 1.0, 0.0)
    results['Static_Threshold'] = evaluate_model("Static Threshold", y_test, dummy_probs, threshold=0.5)

    # Baseline 2: Logistic Regression
    lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
    lr.fit(X_train, y_train)
    lr_probs = lr.predict_proba(X_test)[:, 1]
    results['Logistic_Regression'] = evaluate_model("Logistic Regression", y_test, lr_probs, threshold=0.5)

    # Baseline 3: Random Forest
    rf = RandomForestClassifier(n_estimators=100, max_depth=6, class_weight='balanced', random_state=42)
    rf.fit(X_train, y_train)
    rf_probs = rf.predict_proba(X_test)[:, 1]
    results['Random_Forest'] = evaluate_model("Random Forest", y_test, rf_probs, threshold=0.5)

    return results, lr_probs, rf_probs


def train_lgbm_main(data_path=None, generate_synthetic=False):
    file_path = data_path or 'data_pipeline/data/features_with_experiments.csv'

    if generate_synthetic:
        df = generate_mock_experiments()
        file_path = 'data_pipeline/data/features_with_experiments.csv'
    elif os.path.exists(file_path):
        df = pd.read_csv(file_path)
    else:
        print(f"Error: Dataset not found at {file_path}. Use --generate-synthetic to create demo data or specify --data.")
        sys.exit(1)

    feature_cols = MODEL_FEATURES
    target_col = 'sla_violated_in_horizon'

    # Validate dataset quality and schema before proceeding
    is_valid, violations = validate_feature_dataset(df, target_col=target_col)
    if not is_valid:
        print(f"\nERROR: Dataset validation failed for {file_path} with {len(violations)} violations:")
        for v in violations:
            print(f"  [VIOLATION] {v}")
        print("Training aborted. Existing model artifacts were NOT overwritten.\n")
        sys.exit(1)

    print(f"Dataset validation passed for {file_path} ({len(df)} samples, {len(feature_cols)} features).")

    # Derive data origin dynamically
    if "data_origin" in df.columns and df["data_origin"].nunique() == 1:
        data_origin = str(df["data_origin"].iloc[0])
    elif generate_synthetic or "synthetic" in str(file_path).lower():
        data_origin = "synthetic"
    else:
        data_origin = "mininet_emulation"

    data_hash = sha256_file(file_path)
    git_commit, git_dirty = get_git_info()
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    train_df, val_df, test_df, test_exps = strict_experiment_split(df)

    X_train, y_train = train_df[feature_cols], train_df[target_col]
    X_val, y_val = val_df[feature_cols], val_df[target_col]
    X_test, y_test = test_df[feature_cols], test_df[target_col]

    # Baselines
    baseline_metrics, lr_probs, rf_probs = run_baselines(X_train, y_train, X_test, y_test)

    # Proposed LightGBM
    print("\nTraining Proposed LightGBM Model...")
    train_data = lgb.Dataset(X_train, label=y_train)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

    params = {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'learning_rate': 0.05,
        'num_leaves': 31,
        'is_unbalance': True,
        'verbose': -1,
        'seed': 42
    }

    model = lgb.train(
        params,
        train_data,
        num_boost_round=150,
        valid_sets=[train_data, val_data],
        callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)]
    )

    # Select threshold on VALIDATION set
    val_probs = model.predict(X_val)
    best_threshold = find_best_threshold(y_val, val_probs)
    print(f"Optimal Threshold on Validation Set: {best_threshold:.3f}")

    # Evaluate on TEST set using the validation threshold
    lgb_probs = model.predict(X_test)
    lgb_metrics = evaluate_model("LightGBM", y_test, lgb_probs, threshold=best_threshold)

    # Comparison analysis across baseline & proposed model predictions
    lr_preds = (lr_probs > 0.5).astype(int)
    rf_preds = (rf_probs > 0.5).astype(int)
    lgb_preds = (lgb_probs > best_threshold).astype(int)

    identical_lr_rf = bool(np.array_equal(lr_preds, rf_preds))
    identical_lr_lgb = bool(np.array_equal(lr_preds, lgb_preds))
    prob_diff_lr_lgb = float(np.mean(np.abs(lr_probs - lgb_probs)))

    # Aggregate Evaluation Report
    final_report = {
        'run_id': run_id,
        'evaluation_metadata': {
            'test_experiment_ids': list(test_exps),
            'total_test_samples': len(X_test),
            'positive_class_ratio': float(np.mean(y_test)),
            'lgbm_optimal_threshold': float(best_threshold),
            'identical_predictions_lr_rf': identical_lr_rf,
            'identical_predictions_lr_lgb': identical_lr_lgb,
            'mean_absolute_prob_diff_lr_lgb': prob_diff_lr_lgb,
            'data_origin': data_origin,
            'synthetic_data_warning': "All reported metrics are based on synthetic demonstration data. Do not interpret as real-network performance." if data_origin == "synthetic" else None
        },
        'models': {
            **baseline_metrics,
            'LightGBM': lgb_metrics
        }
    }

    os.makedirs('ml/artifacts', exist_ok=True)

    with open('ml/artifacts/evaluation_report.json', 'w') as f:
        json.dump(final_report, f, indent=4)

    model.save_model('ml/artifacts/lightgbm_model.txt')

    model_metadata = {
        "run_id": run_id,
        "model_version": "1.1.0",
        "feature_schema_version": CURRENT_FEATURE_SCHEMA_VERSION,
        "feature_names": feature_cols,
        "training_data_hash": data_hash,
        "training_commit": git_commit,
        "git_dirty": git_dirty,
        "decision_threshold": float(best_threshold),
        "calibration": {
            "method": None,
            "status": "not_calibrated"
        },
        "creation_time": datetime.now(timezone.utc).isoformat(),
        "data_origin": data_origin
    }
    with open('ml/artifacts/model_metadata.json', 'w') as f:
        json.dump(model_metadata, f, indent=2)

    # Export feature schema
    feature_schema = {
        "schema_version": CURRENT_FEATURE_SCHEMA_VERSION,
        "features": feature_cols,
        "target": target_col,
        "run_id": run_id
    }
    with open('ml/artifacts/feature_schema.json', 'w') as f:
        json.dump(feature_schema, f, indent=2)

    # Export test predictions
    test_results_df = test_df.copy()
    test_results_df['lgbm_predicted_prob'] = lgb_probs
    test_results_df['lgbm_predicted_label'] = lgb_preds
    test_results_df.to_csv('ml/artifacts/test_predictions.csv', index=False)

    print("\n=== FINAL TEST SET EVALUATION ===")
    for m_name, m_stats in final_report['models'].items():
        print(f"--- {m_name} ---")
        print(f"Threshold: {m_stats['threshold']:.3f}")
        print(f"ROC-AUC: {m_stats['roc_auc']:.3f} | PR-AUC: {m_stats['pr_auc']:.3f} | F1: {m_stats['f1']:.3f}")
        print(f"FPR: {m_stats['fpr']:.3f} | Brier: {m_stats['brier_score']:.3f}")
        print(f"Confusion Matrix: {m_stats['confusion_matrix']}")

    print(f"\nArtifacts saved with Run ID: {run_id}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train LightGBM Model for ResiliNet")
    parser.add_argument("--data", type=str, default=None, help="Path to input dataset CSV")
    parser.add_argument("--generate-synthetic", action="store_true", help="Generate new synthetic dataset instead of using existing one")
    args = parser.parse_args()

    train_lgbm_main(data_path=args.data, generate_synthetic=args.generate_synthetic)
