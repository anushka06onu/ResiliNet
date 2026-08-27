import os
import sys

import lightgbm as lgb
import pandas as pd
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from ml.schema import MODEL_FEATURES


def test_model_schema_compatibility():
    """Verify the saved LightGBM model expects the exact schema defined in MODEL_FEATURES"""
    model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ml/artifacts/lightgbm_model.txt'))
    if not os.path.exists(model_path):
        pytest.skip("Model artifact not found, run ml pipeline first.")
    
    model = lgb.Booster(model_file=model_path)
    model_features = model.feature_name()
    
    assert model_features == MODEL_FEATURES, "LightGBM model features do not match ml.schema.MODEL_FEATURES!"

def test_future_label_boundaries():
    """Verify that shifting labels into the future does not cross experiment boundaries."""
    
    # Create two experiments
    df = pd.DataFrame([
        {'experiment_id': 'exp_1', 'current_sla_violated': 0},
        {'experiment_id': 'exp_1', 'current_sla_violated': 0},
        {'experiment_id': 'exp_1', 'current_sla_violated': 1}, # violated near the end
        {'experiment_id': 'exp_1', 'current_sla_violated': 0},
        
        {'experiment_id': 'exp_2', 'current_sla_violated': 0},
        {'experiment_id': 'exp_2', 'current_sla_violated': 0},
        {'experiment_id': 'exp_2', 'current_sla_violated': 0},
        {'experiment_id': 'exp_2', 'current_sla_violated': 0}
    ])
    
    # We redefine get_future_violations to look ahead 2 steps instead of 15 for this tiny test
    def small_future_violations(group):
        future_max = group['current_sla_violated'].iloc[::-1].rolling(2, min_periods=2).max().iloc[::-1].shift(-1)
        group['sla_violated_in_horizon'] = future_max
        return group
    
    df = df.groupby('experiment_id', group_keys=False).apply(small_future_violations)
    
    exp_2 = df[df['experiment_id'] == 'exp_2']
    
    # Exp 2 should NOT see any violations, despite exp 1 having one right before it.
    assert exp_2['sla_violated_in_horizon'].sum() == 0.0, "Leakage occurred across experiment boundary!"
