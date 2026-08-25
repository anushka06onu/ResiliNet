from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import sys
import asyncio
import random
from datetime import datetime
from pydantic import BaseModel
import random
from datetime import datetime

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

# Background task to stream demo telemetry to all connected clients
async def stream_demo_telemetry():
    while True:
        await asyncio.sleep(2.0) # Emit every 2 seconds
        if not manager.active_connections:
            continue
            
class TelemetryPayload(BaseModel):
    switch_id: str
    port_no: str
    features: dict

@app.post("/api/v1/telemetry/ingest")
async def ingest_telemetry(payload: TelemetryPayload):
    event = {
        "mode": "LIVE_LAB",
        "source": "mininet_ryu",
        "type": "link_telemetry",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "experiment_id": "exp_001_live",
        "payload": {
            "link_id": f"{payload.switch_id}-p{payload.port_no}",
            "utilization": round(payload.features.get("utilization", 0.0), 4),
            "latency_ms": 0.0, # Cannot be calculated from pure port stats
            "loss_rate": payload.features.get("tx_dropped", 0.0),
            "predicted_risk": 0.0
        }
    }
    
    # Attempt prediction
    try:
        from app.api.predict import explainer, MODEL_LOADED
        if MODEL_LOADED:
            import pandas as pd
            # Create df matching what the model expects
            # For demonstration, we just pass the features directly, though in reality it might need specific columns
            df = pd.DataFrame([payload.features])
            
            # The model might fail if columns are missing, so we use a try-except
            try:
                prob = explainer.model.predict(df)[0]
                event["payload"]["predicted_risk"] = float(prob)
            except Exception as e:
                print(f"Prediction failed: {e}")
    except Exception as e:
        pass

    await manager.broadcast(event)
    return {"status": "ingested"}

@app.on_event("startup")
async def startup_event():
    # Stop starting the demo telemetry now that we have a live ingest endpoint
    pass

# ---------------------------------------------------------
# System & Topology Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/system/status")
def system_status():
    return {"status": "DEMO DATA", "version": "1.1.0", "active_connections": len(manager.active_connections)}

@app.get("/api/v1/topologies")
def list_topologies():
    return ["small_test", "sndlib_campus", "sndlib_backbone"]

@app.get("/api/v1/topology/current")
def get_current_topology():
    topo_path = 'frontend/public/topology.json'
    if os.path.exists(topo_path):
        with open(topo_path, 'r') as f:
            return json.load(f)
    return {"error": "Topology not active"}

@app.get("/api/v1/links/{link_id}")
def get_link_details(link_id: str):
    return {"link_id": link_id, "capacity": "1Gbps", "current_throughput": "450Mbps"}

# ---------------------------------------------------------
# Flows & QoS Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/flows")
def list_active_flows():
    return [
        {"flow_id": "f_1", "src": "h1", "dst": "h4", "tier": "Critical", "sla_status": "Healthy"},
        {"flow_id": "f_2", "src": "h2", "dst": "h3", "tier": "Background", "sla_status": "Violated"}
    ]

@app.get("/api/v1/flows/{flow_id}")
def get_flow_details(flow_id: str):
    return {"flow_id": flow_id, "path": ["s1", "s3", "s4"], "latency_ms": 12.4}

# ---------------------------------------------------------
# Predictive & Routing Intelligence
# ---------------------------------------------------------
@app.get("/api/v1/predictions")
def get_all_predictions():
    return [{"link_id": "s2-s4", "risk": 0.85, "horizon": "30s"}]

@app.get("/api/v1/predictions/{prediction_id}/explanation")
def get_prediction_explanation(prediction_id: str):
    # Would return SHAP logic
    return {"features": [{"name": "loss_mean_30s", "contribution": 0.45}]}

@app.get("/api/v1/routing/decisions")
def get_routing_decisions():
    return [
        {
            "flow_id": "f_1",
            "original_path": ["s1", "s2", "s4"],
            "proposed_path": ["s1", "s3", "s4"],
            "reason": "Link s2-s4 predicted risk 0.85",
            "applied": True
        }
    ]

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
