#!/usr/bin/env python3

import os

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap


class ResiliNetExplainer:
    def __init__(self, model_path='ml/artifacts/lightgbm_model.txt'):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at {model_path}. Train model first.")
        self.model = lgb.Booster(model_file=model_path)
        self.explainer = shap.TreeExplainer(self.model)
        self.feature_names = self.model.feature_name()

    def get_global_importance(self, X_sample):
        """
        Calculate overall feature importance across a sample of data.
        Returns a dictionary of feature -> mean absolute SHAP value.
        """
        shap_values = self.explainer.shap_values(X_sample)
        # For binary classification, shap_values might be a list of 2 arrays (for LightGBM sometimes)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
            
        mean_abs_shap = np.abs(shap_values).mean(axis=0)
        
        importance_dict = {
            feat: float(val) for feat, val in zip(self.feature_names, mean_abs_shap)
        }
        # Sort by importance descending
        return dict(sorted(importance_dict.items(), key=lambda item: item[1], reverse=True))

    def get_local_explanation(self, x_instance):
        """
        Explain a single prediction (e.g. why is THIS link predicted to fail).
        x_instance should be a 1D numpy array or single-row DataFrame.
        """
        if isinstance(x_instance, pd.Series):
            x_instance = pd.DataFrame(x_instance).T
        elif isinstance(x_instance, np.ndarray) and x_instance.ndim == 1:
            x_instance = x_instance.reshape(1, -1)
            
        shap_values = self.explainer.shap_values(x_instance)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
            
        explanation = {
            'base_value': float(self.explainer.expected_value[1] if isinstance(self.explainer.expected_value, (list, np.ndarray)) else self.explainer.expected_value),
            'features': []
        }
        
        for i, feat in enumerate(self.feature_names):
            explanation['features'].append({
                'name': feat,
                'value': float(x_instance.iloc[0, i] if isinstance(x_instance, pd.DataFrame) else x_instance[0, i]),
                'shap_contribution': float(shap_values[0, i])
            })
            
        # Sort features by absolute contribution to see the biggest drivers first
        explanation['features'].sort(key=lambda x: abs(x['shap_contribution']), reverse=True)
        
        return explanation

if __name__ == '__main__':
    from train_lightgbm import load_data
    print("Testing SHAP Explainer...")
    try:
        explainer = ResiliNetExplainer()
        X, y = load_data('data_pipeline/data/features.csv')
        sample = X.head(100)
        
        print("\n--- Global Feature Importance ---")
        global_imp = explainer.get_global_importance(sample)
        for k, v in list(global_imp.items())[:5]:
            print(f"{k}: {v:.4f}")
            
        print("\n--- Local Explanation (Row 0) ---")
        local_exp = explainer.get_local_explanation(X.iloc[0])
        print(f"Base Value: {local_exp['base_value']:.4f}")
        for feat in local_exp['features'][:3]:
            print(f"  {feat['name']}: {feat['value']:.2f} -> contribution: {feat['shap_contribution']:+.4f}")
            
    except Exception as e:
        print(f"Error running explainer test: {e}")
