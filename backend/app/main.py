from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import sys
import asyncio
import random
from datetime import datetime
from pydantic import BaseModel

# Import routers
try:
    from app.api.predict import router as predict_router
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from api.predict import router as predict_router

app = FastAPI(
    title="ResiliNet API",
    description="Network Digital Twin Backend for Predictive QoS and Routing",
    version="1.1.0"
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predict_router, prefix="/api/v1", tags=["ML"])

# ---------------------------------------------------------
# WebSockets: Live Streaming Connection
# ---------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # The client might send control messages
            data = await websocket.receive_text()
            print(f"WS Client says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

class TelemetryPayload(BaseModel):
    switch_id: str
    port_no: str
    features: dict

latest_features = {}
last_telemetry_timestamp = None

# A rolling buffer for historical telemetry values to compute rolling stats
# Format: { link_id: [(timestamp, rx_bytes, tx_dropped, tx_packets)] }
import sys
from pathlib import Path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from data_pipeline.feature_engineering import FeaturePipeline
feature_pipeline = FeaturePipeline()

@app.post("/api/v1/telemetry/ingest")
async def ingest_telemetry(payload: TelemetryPayload):
    global last_telemetry_timestamp
    last_telemetry_timestamp = datetime.utcnow()
    
    link_id = f"{payload.switch_id}-p{payload.port_no}"
    
    # payload.features currently has rx_bytes, tx_bytes, control_plane_rtt_ms, loss_percent, etc.
    # We pass it to the FeaturePipeline
    computed_features = feature_pipeline.process_raw_telemetry(
        link_id=link_id, 
        raw_metrics=payload.features,
        timestamp=last_telemetry_timestamp
    )
    
    if computed_features.get("status") == "INSUFFICIENT_DATA":
        latest_features[link_id] = payload.features # Store raw until warm
        return {"status": "warming_up", "message": "Gathering more telemetry"}
    
    # Store globally so frontend can poll it
    latest_features[link_id] = computed_features

    event = {
        "mode": "LIVE LAB",
        "source": "mininet_ryu",
        "type": "link_telemetry",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "experiment_id": "demo_scenario_001",
        "payload": {
            "link_id": link_id,
            "utilization": round(computed_features.get("utilization", 0.0), 4),
            "latency_ms": computed_features.get("control_plane_rtt_ms"),
            "loss_rate": computed_features.get("loss_mean_30s", 0.0),
            "predicted_risk": None,
            "prediction_status": "unavailable"
        }
    }
    
    # Attempt prediction
    try:
        from app.api.predict import model, MODEL_LOADED, DECISION_THRESHOLD
        if MODEL_LOADED:
            import pandas as pd
            import sys
            from pathlib import Path
            project_root = str(Path(__file__).resolve().parents[2])
            if project_root not in sys.path:
                sys.path.append(project_root)
            from ml.schema import MODEL_FEATURES
            
            df = pd.DataFrame(
                [computed_features],
                columns=MODEL_FEATURES
            ).apply(pd.to_numeric, errors="coerce")
            
            try:
                prob = model.predict(df)[0]
                event["payload"]["predicted_risk"] = float(prob)
                event["payload"]["is_violation_predicted"] = bool(prob > DECISION_THRESHOLD)
                event["payload"]["prediction_status"] = "success"
            except Exception as e:
                print(f"Prediction failed: {e}")
                event["payload"]["prediction_status"] = "inference_failed"
        else:
            event["payload"]["prediction_status"] = "model_unavailable"
    except Exception as e:
        event["payload"]["prediction_status"] = "inference_failed"
        print(f"Prediction exception: {e}")

    # Pass the event to the Orchestrator to evaluate flows and routing
    orchestrator.handle_telemetry_event(event)

    await manager.broadcast(event)
    return {"status": "ingested"}

@app.on_event("startup")
async def startup_event():
    # Stop starting the demo telemetry now that we have a live ingest endpoint
    pass

# ---------------------------------------------------------
# System & Topology Endpoints
# ---------------------------------------------------------
active_live_topology = None

from app.services.orchestrator import orchestrator

@app.post("/api/v1/topology/ingest")
async def ingest_topology(payload: dict):
    global active_live_topology
    active_live_topology = payload
    orchestrator.load_topology(payload)
    return {"status": "topology_ingested"}

@app.get("/api/v1/system/status")
def system_status():
    mode = "DEMO DATA"
    if last_telemetry_timestamp:
        dt = (datetime.utcnow() - last_telemetry_timestamp).total_seconds()
        if dt <= 10.0:
            mode = "LIVE LAB"
            
    return {"status": mode, "version": "1.1.0", "active_connections": len(manager.active_connections)}

@app.get("/api/v1/topologies")
def list_topologies():
    return ["small_test", "sndlib_campus", "sndlib_backbone"]

@app.get("/api/v1/topology/current")
def get_current_topology():
    if active_live_topology is not None:
        return active_live_topology
        
    topo_path = 'frontend/public/topology.json'
    if os.path.exists(topo_path):
        with open(topo_path, 'r') as f:
            return json.load(f)
    return {"nodes": [], "links": [], "mode": "DEMO DATA"}

@app.get("/api/v1/links/{link_id}")
def get_link_details(link_id: str):
    return {"link_id": link_id, "capacity": "10Mbps", "current_throughput": "4.5Mbps"}

@app.get("/api/v1/links/{link_id}/latest-prediction")
def get_latest_prediction(link_id: str):
    features = latest_features.get(link_id, {})
    
    try:
        from app.api.predict import model, explainer, MODEL_LOADED, EXPLAINER_LOADED, DECISION_THRESHOLD
        if MODEL_LOADED and features:
            import pandas as pd
            import sys
            from pathlib import Path
            project_root = str(Path(__file__).resolve().parents[2])
            if project_root not in sys.path:
                sys.path.append(project_root)
            from ml.schema import MODEL_FEATURES
            
            try:
                df = pd.DataFrame(
                    [features],
                    columns=MODEL_FEATURES
                ).apply(pd.to_numeric, errors="coerce")
            except Exception as e:
                return {
                    "mode": "LIVE LAB",
                    "prediction_status": "schema_mismatch",
                    "error": "feature_schema_mismatch",
                    "detail": str(e)
                }
            
            try:
                prob = float(model.predict(df)[0])
            except Exception as e:
                return {
                    "mode": "LIVE LAB",
                    "prediction_status": "inference_failed",
                    "error": "inference_failed",
                    "detail": str(e)
                }
                
            explanation = {"status": "unavailable", "reason": "explainer_not_loaded"}
            if EXPLAINER_LOADED:
                try:
                    explanation = explainer.get_local_explanation(df)
                    import math
                    for f in explanation.get("features", []):
                        if isinstance(f.get("value"), float) and math.isnan(f["value"]):
                            f["value"] = None
                except Exception as e:
                    explanation = {"status": "unavailable", "reason": "explainer_failed", "detail": str(e)}
                    
            return {
                "mode": "LIVE LAB",
                "prediction_status": "success",
                "predict": {
                    "link_id": link_id,
                    "congestion_probability": prob,
                    "is_violation_predicted": bool(prob > DECISION_THRESHOLD),
                    "horizon": "30s"
                },
                "explain": explanation
            }
        else:
            return {
                "mode": "LIVE LAB",
                "prediction_status": "model_unavailable" if not MODEL_LOADED else "insufficient_data",
                "error": "model_unavailable" if not MODEL_LOADED else "no_features"
            }
    except Exception as e:
        return {
            "mode": "LIVE LAB",
            "prediction_status": "inference_failed",
            "error": "internal_error",
            "detail": str(e)
        }

# ---------------------------------------------------------
# Flows & QoS Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/flows")
def list_active_flows():
    # Return actual flows from orchestrator
    flows = list(orchestrator.flows.values())
    if not flows:
        return []
    return flows

@app.get("/api/v1/flows/{flow_id}")
def get_flow_details(flow_id: str):
    if flow_id in orchestrator.flows:
        flow = orchestrator.flows[flow_id]
        return {
            "flow_id": flow_id,
            "src": flow["src"],
            "dst": flow["dst"],
            "current_path": flow["current_path"],
            "sla": {"max_latency_ms": 20, "max_loss_percent": 1.0},
            "metrics": {"latency_ms": 15, "loss_percent": 0.0} # Needs real metrics
        }
    return {"error": "Flow not found"}

# ---------------------------------------------------------
# Routing Decisions Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/routing/decisions")
def list_routing_decisions():
    return orchestrator.routing_decisions

# ---------------------------------------------------------
# Experiment Control & Replay
# ---------------------------------------------------------
@app.get("/api/v1/experiments")
def list_experiments():
    return [{"id": "exp_001", "topology": "small_test", "duration": "300s"}]

@app.get("/api/v1/experiments/{id}")
def get_experiment(id: str):
    return {"id": id, "status": "completed"}

@app.post("/api/v1/experiments/{id}/start")
def start_experiment(id: str):
    return {"status": "started", "experiment": id}

@app.post("/api/v1/experiments/{id}/pause")
def pause_experiment(id: str):
    return {"status": "paused", "experiment": id}

@app.post("/api/v1/experiments/{id}/stop")
def stop_experiment(id: str):
    return {"status": "stopped", "experiment": id}

@app.get("/api/v1/replay/{experiment_id}")
def replay_experiment(experiment_id: str):
    return {"status": "replaying", "experiment": experiment_id}
