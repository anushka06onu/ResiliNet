from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import sys
import os

# Add root to sys.path to import ml module
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

try:
    from ml.explain import ResiliNetExplainer
    import numpy as np
    import pandas as pd
    import json
    from pathlib import Path
    
    ROOT = Path(__file__).resolve().parents[3]
    MODEL_PATH = ROOT / "ml" / "artifacts" / "lightgbm_model.txt"
    EVAL_PATH = ROOT / "ml" / "artifacts" / "evaluation_report.json"
    
    explainer = ResiliNetExplainer(model_path=str(MODEL_PATH))
    MODEL_LOADED = True
    
    DECISION_THRESHOLD = 0.5
    try:
        with open(EVAL_PATH, "r") as f:
            eval_data = json.load(f)
            DECISION_THRESHOLD = eval_data.get("evaluation_metadata", {}).get("lgbm_optimal_threshold", 0.5)
    except Exception:
        pass
        
    from ml.schema import MODEL_FEATURES
except Exception as e:
    print(f"Warning: Failed to load ML Explainer: {e}")
    MODEL_LOADED = False
    DECISION_THRESHOLD = 0.5

router = APIRouter()

class FeatureVector(BaseModel):
    switch_id: str
    port_no: str
    features: Dict[str, float]

@router.post("/predict")
async def predict_congestion(data: FeatureVector):
    if not MODEL_LOADED:
        raise HTTPException(status_code=503, detail="ML Model not loaded")
        
    try:
        # Convert to DataFrame using proper schema
        df = pd.DataFrame([data.features], columns=MODEL_FEATURES).apply(pd.to_numeric, errors="coerce")
        
        # Predict probability
        prob = explainer.model.predict(df)[0]
        
        return {
            "switch_id": data.switch_id,
            "port_no": data.port_no,
            "congestion_probability": float(prob),
            "is_violation_predicted": bool(prob > DECISION_THRESHOLD),
            "threshold_used": DECISION_THRESHOLD
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/explain")
async def explain_prediction(data: FeatureVector):
    if not MODEL_LOADED:
        raise HTTPException(status_code=503, detail="ML Model not loaded")
        
    try:
        df = pd.DataFrame([data.features])
        explanation = explainer.get_local_explanation(df)
        
        return {
            "switch_id": data.switch_id,
            "port_no": data.port_no,
            "base_value": explanation.get('base_value', 0.0),
            "features": explanation.get('features', [])
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
