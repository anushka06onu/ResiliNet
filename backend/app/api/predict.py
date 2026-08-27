import os
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add root to sys.path to import ml module
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = ROOT / "ml" / "artifacts" / "lightgbm_model.txt"
EVAL_PATH = ROOT / "ml" / "artifacts" / "evaluation_report.json"
META_PATH = ROOT / "ml" / "artifacts" / "model_metadata.json"
DECISION_THRESHOLD = 0.5
MODEL_LOADED = False
EXPLAINER_LOADED = False
MODEL_METADATA = None

model = None
explainer = None

# 1. Attempt to load the LightGBM model and validate metadata
try:
    import lightgbm as lgb
    from ml.schema import MODEL_FEATURES, CURRENT_FEATURE_SCHEMA_VERSION, ModelMetadata

    if MODEL_PATH.exists():
        # Validate metadata if present
        if META_PATH.exists():
            with open(META_PATH, "r") as f:
                meta_dict = json.load(f)
                MODEL_METADATA = ModelMetadata(**meta_dict)
                if MODEL_METADATA.feature_schema_version != CURRENT_FEATURE_SCHEMA_VERSION:
                    raise ValueError(
                        f"Incompatible model schema version: {MODEL_METADATA.feature_schema_version} "
                        f"(expected {CURRENT_FEATURE_SCHEMA_VERSION})"
                    )
                DECISION_THRESHOLD = MODEL_METADATA.decision_threshold

        model = lgb.Booster(model_file=str(MODEL_PATH))
        MODEL_LOADED = True

        if not MODEL_METADATA and EVAL_PATH.exists():
            try:
                with open(EVAL_PATH, "r") as f:
                    eval_data = json.load(f)
                    DECISION_THRESHOLD = eval_data.get("evaluation_metadata", {}).get("lgbm_optimal_threshold", 0.5)
            except Exception as e:
                import logging
                logging.warning(f"Failed to read threshold from evaluation report: {e}")
    else:
        print(f"Warning: Model file not found at {MODEL_PATH}")
except Exception as e:
    MODEL_LOADED = False
    print(f"Warning: Failed to load/validate LightGBM model: {e}")

# 2. Attempt to load the Explainer (optional)
if MODEL_LOADED:
    try:
        from ml.explain import ResiliNetExplainer
        explainer = ResiliNetExplainer(model_path=str(MODEL_PATH))
        EXPLAINER_LOADED = True
    except Exception as e:
        print(f"Warning: Failed to load ML Explainer (SHAP unavailable): {e}")

from pydantic import BaseModel, Field

router = APIRouter()

class FeatureVector(BaseModel):
    switch_id: str
    port_no: int = Field(ge=1)
    features: dict[str, float]

@router.post("/predict")
async def predict_congestion(data: FeatureVector):
    if not MODEL_LOADED:
        raise HTTPException(status_code=503, detail="ML Model not loaded")
        
    try:
        # Convert to DataFrame using proper schema
        df = pd.DataFrame([data.features], columns=MODEL_FEATURES).apply(pd.to_numeric, errors="coerce")
        
        # Predict probability
        prob = model.predict(df)[0]
        
        return {
            "switch_id": data.switch_id,
            "port_no": data.port_no,
            "congestion_probability": float(prob),
            "is_violation_predicted": bool(prob > DECISION_THRESHOLD),
            "threshold_used": DECISION_THRESHOLD
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/explain")
async def explain_prediction(data: FeatureVector):
    if not EXPLAINER_LOADED:
        raise HTTPException(status_code=503, detail="ML Explainer (SHAP) unavailable")
        
    try:
        df = pd.DataFrame([data.features], columns=MODEL_FEATURES).apply(pd.to_numeric, errors="coerce")
        explanation = explainer.get_local_explanation(df)
        
        return {
            "switch_id": data.switch_id,
            "port_no": data.port_no,
            "base_value": explanation.get('base_value', 0.0),
            "features": explanation.get('features', [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
