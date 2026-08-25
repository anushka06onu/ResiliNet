#!/usr/bin/env python3

import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import pickle
import os

def load_data(file_path):
    # In a real run, this would load the output from data_pipeline
    # For now, we mock a structure if the file doesn't exist
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} not found. Using dummy data for testing.")
        np.random.seed(42)
        X = np.random.rand(1000, 5)
        y = np.random.randint(0, 2, 1000)
        return X, y
    
    df = pd.read_csv(file_path)
    # Define feature columns based on feature_engineering
    feature_cols = [c for c in df.columns if 'mean' in c or 'max' in c or 'rate' in c]
    X = df[feature_cols].fillna(0).values
    y = df['sla_violated_in_horizon'].values
    return X, y

def train_baseline():
    X, y = load_data('data_pipeline/data/features.csv')
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('classifier', LogisticRegression(class_weight='balanced', max_iter=1000))
    ])

    print("Training Logistic Regression Baseline...")
    pipeline.fit(X_train, y_train)
    
    score = pipeline.score(X_test, y_test)
    print(f"Baseline Accuracy: {score:.4f}")
    
    os.makedirs('ml/artifacts', exist_ok=True)
    with open('ml/artifacts/logistic_model.pkl', 'wb') as f:
        pickle.dump(pipeline, f)
    print("Saved baseline model to ml/artifacts/logistic_model.pkl")

if __name__ == '__main__':
    train_baseline()
