#!/usr/bin/env python3

import os
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
import argparse
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix, brier_score_loss
)

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.append(project_root)
from ml.schema import MODEL_FEATURES

def generate_mock_experiments():
    """
    Generate a highly realistic mock dataset with explicit experiment IDs.
    NOTE: All metrics are based on synthetic demonstration data and must not 
    be interpreted as real-network performance.
    """
    print("WARNING: Generating synthetic demonstration dataset. Do not interpret as real network performance.")
    np.random.seed(42)
    experiments = [f"exp_{str(i).zfill(3)}" for i in range(1, 101)] # 100 experiments
    
    rows = []
    for exp in experiments:
        num_samples = np.random.randint(50, 150)
        # Induce congestion in ~30% of experiments
        is_congested_exp = np.random.rand() < 0.3
        congestion_start = np.random.randint(20, num_samples - 20) if (is_congested_exp and num_samples > 40) else num_samples + 1
        
        for t in range(num_samples):
            # Temporal dynamics
            congested = (t >= congestion_start)
            loss_mean = np.random.exponential(2.5) if congested else np.random.exponential(0.1)
            tx_dropped = np.random.poisson(5) if congested else np.random.poisson(0)
            # Control-plane RTT is usually lower than data-plane latency. 
            # Assumption: Uncongested control plane responds in ~3ms. Under high data-plane congestion, 
            # switch CPU/buffer pressure increases control-plane RTT to ~15ms.
            latency = np.random.normal(15, 5) if congested else np.random.normal(3, 1)
            
            rows.append({
                'experiment_id': exp,
                'timestamp': t,
                'src_switch': 's1',
                'dst_switch': 's2',
                'loss_mean_30s': loss_mean,
                'tx_dropped_max': tx_dropped,
                'control_plane_rtt_ms': latency,
                'rx_bytes_slope': np.random.normal(100, 50),
                'tx_bytes_rate': np.random.uniform(5000, 15000),
                'current_sla_violated': 1 if (loss_mean > 2.0 or latency > 20.0) else 0
            })
            
    df = pd.DataFrame(rows)
    
    # Calculate future-shifted 30-second label (approx 15 intervals of 2s)
    # Perform shift inside the group to avoid cross-experiment leakage
    # Drop rows without a full 15-step horizon
    def get_future_violations(group):
        # Rolling max looking ahead 15 steps. Note that rolling works backwards,
        # so we reverse the series, roll, and reverse back.
        # But for the last 15 rows, they don't have a full horizon, so we set them to NaN
        future_max = group['current_sla_violated'].iloc[::-1].rolling(15, min_periods=15).max().iloc[::-1].shift(-1)
        group['sla_violated_in_horizon'] = future_max
        return group

    df = df.groupby('experiment_id', group_keys=False).apply(get_future_violations)
    
    # Drop the rows that do not have a full horizon
    df = df.dropna(subset=['sla_violated_in_horizon'])
    df['sla_violated_in_horizon'] = df['sla_violated_in_horizon'].astype(int)
    
    # Save the mock dataset to disk for the rest of the pipeline to see
    os.makedirs('data_pipeline/data', exist_ok=True)
    df.to_csv('data_pipeline/data/features_with_experiments.csv', index=False)
    return df

def strict_experiment_split(df):
    """
    Splits the dataset strictly by complete experimental runs (60/20/20)
    to prevent temporal data leakage.
    """
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
    print(f"Train: {len(train_exps)} exps | Val: {len(val_exps)} exps | Test: {len(test_exps)} exps")
    
    return train_df, val_df, test_df, test_exps

def find_best_threshold(y_true, y_prob):
    thresholds = np.linspace(0.01, 0.99, 99)
    best_thresh = 0.5
    best_f1 = 0
    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = t
    return best_thresh

def evaluate_model(name, y_true, y_prob, threshold=0.5):
    y_pred = (y_prob >= threshold).astype(int)
    metrics = {
        'threshold': float(threshold),
        'accuracy': float(accuracy_score(y_true, y_pred)),
        'precision': float(precision_score(y_true, y_pred, zero_division=0)),
        'recall': float(recall_score(y_true, y_pred, zero_division=0)),
        'f1': float(f1_score(y_true, y_pred, zero_division=0)),
        'roc_auc': float(roc_auc_score(y_true, y_prob)),
        'pr_auc': float(average_precision_score(y_true, y_prob)),
        'brier_score': float(brier_score_loss(y_true, y_prob))
    }
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0,1]).ravel()
    metrics['fpr'] = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    metrics['confusion_matrix'] = {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}
    return metrics

def run_baselines(X_train, y_train, X_test, y_test):
    print("\nRunning Baselines...")
    results = {}
    
    # 1. Static Rule (e.g. if latency > 20ms -> alert)
    print("Evaluating Static Threshold Baseline...")
    static_probs = (X_test['control_plane_rtt_ms'] > 20.0).astype(float).values
    results['Static_Threshold'] = evaluate_model("Static_Threshold", y_test, static_probs, threshold=0.5)
    
    # 2. Logistic Regression
    print("Training Logistic Regression Baseline...")
    lr = LogisticRegression(max_iter=1000)
    lr.fit(X_train, y_train)
    lr_probs = lr.predict_proba(X_test)[:, 1]
    # Use fixed 0.5 for baselines or optimize as well
    results['Logistic_Regression'] = evaluate_model("Logistic_Regression", y_test, lr_probs, threshold=0.5)
    
    # 3. Random Forest
    print("Training Random Forest Baseline...")
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X_train, y_train)
    rf_probs = rf.predict_proba(X_test)[:, 1]
    results['Random_Forest'] = evaluate_model("Random_Forest", y_test, rf_probs, threshold=0.5)
    
    return results

def train_lgbm_main(generate_synthetic=False):
    file_path = 'data_pipeline/data/features_with_experiments.csv'
    if generate_synthetic or not os.path.exists(file_path):
        df = generate_mock_experiments()
    else:
        df = pd.read_csv(file_path)
        
    feature_cols = MODEL_FEATURES
    target_col = 'sla_violated_in_horizon'
    
    train_df, val_df, test_df, test_exps = strict_experiment_split(df)
    
    X_train, y_train = train_df[feature_cols], train_df[target_col]
    X_val, y_val = val_df[feature_cols], val_df[target_col]
    X_test, y_test = test_df[feature_cols], test_df[target_col]
    
    # Baselines
    baseline_metrics = run_baselines(X_train, y_train, X_test, y_test)
    
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
    
    # Aggregate Evaluation Report
    final_report = {
        'evaluation_metadata': {
            'test_experiment_ids': list(test_exps),
            'total_test_samples': len(X_test),
            'positive_class_ratio': float(np.mean(y_test)),
            'lgbm_optimal_threshold': float(best_threshold),
            'synthetic_data_warning': "All reported metrics are based on synthetic demonstration data. Do not interpret as real-network performance."
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
    
    print("\n=== FINAL TEST SET EVALUATION ===")
    for m_name, m_stats in final_report['models'].items():
        print(f"--- {m_name} ---")
        print(f"Threshold: {m_stats['threshold']:.3f}")
        print(f"ROC-AUC: {m_stats['roc_auc']:.3f} | PR-AUC: {m_stats['pr_auc']:.3f} | F1: {m_stats['f1']:.3f}")
        print(f"FPR: {m_stats['fpr']:.3f} | Brier: {m_stats['brier_score']:.3f}")
        print(f"Confusion Matrix: {m_stats['confusion_matrix']}")
        
    print("\nEvaluation report saved to ml/artifacts/evaluation_report.json")
    print("Saved LightGBM model to ml/artifacts/lightgbm_model.txt")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train LightGBM Model for ResiliNet")
    parser.add_argument("--generate-synthetic", action="store_true", help="Generate new synthetic dataset instead of using existing one")
    args = parser.parse_args()
    
    train_lgbm_main(generate_synthetic=args.generate_synthetic)
