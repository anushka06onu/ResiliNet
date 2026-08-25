#!/usr/bin/env python3

import lightgbm as lgb
import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, roc_auc_score, average_precision_score, confusion_matrix
import os
from train_lightgbm import load_data
from sklearn.model_selection import train_test_split

def evaluate_model():
    model_path = 'ml/artifacts/lightgbm_model.txt'
    if not os.path.exists(model_path):
        print("Model not found. Run train_lightgbm.py first.")
        return

    model = lgb.Booster(model_file=model_path)
    X, y = load_data('data_pipeline/data/features.csv')
    
    # We evaluate on the test split
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    y_pred_prob = model.predict(X_test)
    y_pred = (y_pred_prob > 0.5).astype(int)
    
    print("--- LightGBM Evaluation ---")
    print(classification_report(y_test, y_pred))
    
    roc_auc = roc_auc_score(y_test, y_pred_prob)
    pr_auc = average_precision_score(y_test, y_pred_prob)
    
    print(f"ROC-AUC: {roc_auc:.4f}")
    print(f"PR-AUC:  {pr_auc:.4f}")
    
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred))

if __name__ == '__main__':
    evaluate_model()
