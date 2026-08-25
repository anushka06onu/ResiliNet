#!/usr/bin/env python3

import lightgbm as lgb
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import pickle
import os

def load_data(file_path):
    # Mock data logic as before
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} not found. Using dummy data for LightGBM.")
        np.random.seed(42)
        X = pd.DataFrame(np.random.rand(5000, 10), columns=[f'feat_{i}' for i in range(10)])
        y = np.random.randint(0, 2, 5000)
        return X, y
    
    df = pd.read_csv(file_path)
    feature_cols = [c for c in df.columns if 'mean' in c or 'max' in c or 'rate' in c]
    X = df[feature_cols].fillna(0)
    y = df['sla_violated_in_horizon']
    return X, y

def train_lgbm():
    X, y = load_data('data_pipeline/data/features.csv')
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    train_data = lgb.Dataset(X_train, label=y_train)
    test_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

    params = {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'learning_rate': 0.05,
        'num_leaves': 31,
        'is_unbalance': True, # Handle class imbalance for SLA violations
        'verbose': -1
    }

    print("Training LightGBM Model...")
    model = lgb.train(
        params,
        train_data,
        num_boost_round=100,
        valid_sets=[train_data, test_data]
    )
    
    os.makedirs('ml/artifacts', exist_ok=True)
    model.save_model('ml/artifacts/lightgbm_model.txt')
    print("Saved LightGBM model to ml/artifacts/lightgbm_model.txt")

if __name__ == '__main__':
    train_lgbm()
