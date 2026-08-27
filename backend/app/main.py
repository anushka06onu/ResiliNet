import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

project_root = Path(__file__).resolve().parents[2]

# Import routers
try:
    from app.api.predict import router as predict_router
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from api.predict import router as predict_router

from typing import List, Optional

class TopologyNode(BaseModel):
    id: str
    type: str

class TopologyLink(BaseModel):
    source: str
    source_port: Optional[str] = None
    target: str
    target_port: Optional[str] = None

class TopologySchema(BaseModel):
    nodes: List[TopologyNode]
    links: List[TopologyLink]
    mode: Optional[str] = None

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

class TelemetryMetrics(BaseModel):
    rx_bytes: float = Field(..., allow_inf_nan=False)
    tx_bytes: float = Field(..., allow_inf_nan=False)
    control_plane_rtt_ms: float = Field(..., allow_inf_nan=False)
    tx_dropped: float = Field(..., allow_inf_nan=False)
    loss_percent: float = Field(..., allow_inf_nan=False)
    utilization: float = Field(..., allow_inf_nan=False)

class TelemetryPayload(BaseModel):
    switch_id: str
    port_no: str
    features: TelemetryMetrics

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
        raw_metrics=payload.features.dict(),
        timestamp=last_telemetry_timestamp
    )

    if computed_features.get("status") == "INSUFFICIENT_DATA":
        latest_features[link_id] = payload.features.dict() # Store raw until warm
        return {"status": "warming_up", "message": "Gathering more telemetry"}

    if computed_features.get("status") == "STALE_DATA":
        return {"status": "dropped", "message": "Stale metric"}

    # Store globally so frontend can poll it
    latest_features[link_id] = computed_features


    # Append to telemetry history
    tel_record = computed_features.copy()
    tel_record['timestamp'] = last_telemetry_timestamp.isoformat() + "Z"
    tel_record['link_id'] = link_id
    telemetry_history.append(tel_record)

    is_violation_actual = computed_features.get("control_plane_rtt_ms", 0.0) > 50.0

    event = {
        "mode": "LIVE LAB",
        "source": "mininet_ryu",
        "type": "link_telemetry",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "experiment_id": orchestrator.active_experiment_id or "unknown",
        "payload": {
            "link_id": link_id,
            "utilization": round(computed_features.get("utilization", 0.0), 4),
            "latency_ms": computed_features.get("control_plane_rtt_ms"),
            "loss_rate": computed_features.get("loss_mean_30s", 0.0),
            "predicted_risk": None,
            "prediction_status": "unavailable",
            "is_violation_actual": is_violation_actual
        }
    }


    # Attempt prediction
    try:
        from app.api.predict import DECISION_THRESHOLD, MODEL_LOADED, model
        if MODEL_LOADED:
            import sys
            from pathlib import Path

            import pandas as pd
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

                # Append to prediction history
                pred_record = computed_features.copy()
                pred_record['timestamp'] = event["timestamp"]
                pred_record['link_id'] = link_id
                pred_record['predicted_risk'] = float(prob)
                prediction_history.append(pred_record)
            except Exception as e:
                print(f"Prediction failed: {e}")
                event["payload"]["prediction_status"] = "inference_failed"
        else:
            event["payload"]["prediction_status"] = "model_unavailable"
    except Exception as e:
        event["payload"]["prediction_status"] = "inference_failed"
        print(f"Prediction exception: {e}")

    # Pass the event to the Orchestrator to evaluate flows and routing
    # Offload to a background thread to prevent blocking the async event loop with subprocess and sleep calls
    asyncio.create_task(asyncio.to_thread(orchestrator.handle_telemetry_event, event))

    await manager.broadcast(event)
    return {"status": "ingested"}

@app.on_event("startup")
async def startup_event():
    # Stop starting the demo telemetry now that we have a live ingest endpoint
    orchestrator.initialize_db()

# ---------------------------------------------------------
# System & Topology Endpoints
# ---------------------------------------------------------
active_live_topology = None

from app.services.orchestrator import orchestrator


@app.post("/api/v1/topology/ingest")
async def ingest_topology(payload: TopologySchema):
    global active_live_topology
    active_live_topology = payload.dict()
    orchestrator.load_topology(active_live_topology)
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
        from app.api.predict import (
            DECISION_THRESHOLD,
            EXPLAINER_LOADED,
            MODEL_LOADED,
            explainer,
            model,
        )
        if not MODEL_LOADED:
            raise HTTPException(status_code=503, detail="Model unavailable")

        if MODEL_LOADED and features:
            import sys
            from pathlib import Path

            import pandas as pd
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
            "metrics": {"latency_ms": None, "loss_percent": None, "status": "unavailable"}
        }
    raise HTTPException(status_code=404, detail="Flow not found")

# ---------------------------------------------------------
# Routing Decisions Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/routing/decisions")
def list_routing_decisions():
    return orchestrator.routing_decisions

# ---------------------------------------------------------
# ---------------------------------------------------------
# Experiment Control & Replay
# ---------------------------------------------------------
import subprocess


class ExperimentManager:
    def __init__(self):
        self.active_processes = {}
        self.historical_records = {}

    def start(self, id: str, config: "ExperimentConfig"):
        if id in self.active_processes and self.active_processes[id].poll() is None:
            return False

        experiment_script = Path(project_root) / "experiments" / "run_experiment.py"
        cmd = ["python3", str(experiment_script), "--scenario", config.scenario, "--duration", str(config.duration), "--seed", str(config.seed), "--experiment-id", id, "--policy", config.policy]
        proc = subprocess.Popen(cmd, cwd=project_root)
        self.active_processes[id] = proc
        self.historical_records[id] = {"status": "STARTING", "proc": proc}
        return True

    def stop(self, id: str):
        if id not in self.active_processes:
            return False

        proc = self.active_processes[id]
        if proc.poll() is None:
            import signal
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        self.historical_records[id]["status"] = "STOPPED"
        del self.active_processes[id]
        return True

    def status(self, id: str):
        if id in self.active_processes:
            proc = self.active_processes[id]
            if proc.poll() is None:
                return "running"
            else:
                code = proc.returncode
                self.historical_records[id]["status"] = "completed" if code == 0 else f"failed (code {code})"
                del self.active_processes[id]
                return self.historical_records[id]["status"]

        if id in self.historical_records:
            return self.historical_records[id]["status"]

        return "unknown"

experiment_manager = ExperimentManager()

@app.get("/api/v1/experiments")
def list_experiments():
    import json
    results = []

    # Add currently active
    for exp_id, proc in experiment_manager.active_processes.items():
        if proc.poll() is None:
            results.append({
                "id": exp_id,
                "status": "running"
            })

    # Add finished from results directory
    results_dir = Path(project_root) / "experiments" / "results"
    for manifest_path in results_dir.glob("*_manifest.json"):
        try:
            with manifest_path.open("r", encoding="utf-8") as file:
                manifest = json.load(file)

            results.append({
                "id": manifest.get("experiment_id"),
                "status": manifest.get("status", "unknown"),
                "scenario": manifest.get("scenario"),
                "seed": manifest.get("seed"),
            })
        except Exception:
            pass

    return results

@app.get("/api/v1/experiments/{id}")
def get_experiment(id: str):
    status = experiment_manager.status(id)
    if status == "unknown":
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"id": id, "status": status}


class ExperimentConfig(BaseModel):
    scenario: Literal["normal", "gradual_congestion", "sudden_surge"] = "normal"
    duration: int = Field(60, ge=10, le=3600)
    seed: int = 42
    policy: Literal["static", "reactive", "predictive"] = "predictive"


telemetry_history = []
prediction_history = []

import re

@app.post("/api/v1/experiments/{id}/start")
def start_experiment(id: str, config: ExperimentConfig = None):
    if not re.match(r"^[a-zA-Z0-9_-]+$", id):
        raise HTTPException(status_code=422, detail="Invalid experiment ID")

    global telemetry_history, prediction_history
    telemetry_history = []
    prediction_history = []
    orchestrator.routing_decisions = []
    feature_pipeline.link_history.clear()


    if config is None:
        config = ExperimentConfig()

    orchestrator.begin_experiment(id, config.policy)

    if not experiment_manager.start(id, config):
        raise HTTPException(status_code=409, detail="Experiment already running")

    return {"status": "STARTING", "experiment": id, "scenario": config.scenario}

@app.post("/api/v1/experiments/{id}/pause")
def pause_experiment(id: str):
    # Respond with HTTP 501 Not Implemented instead of misleading status
    from fastapi import HTTPException
    raise HTTPException(status_code=501, detail="Pause not supported directly in Mininet yet")

@app.post("/api/v1/experiments/{id}/stop")
def stop_experiment(id: str):
    experiment_manager.stop(id)

    # Dump artifacts
    import os

    import pandas as pd
    results_dir = Path(project_root) / 'experiments' / 'results'
    os.makedirs(results_dir, exist_ok=True)

    if telemetry_history:
        pd.DataFrame(telemetry_history).to_csv(results_dir / f"{id}_telemetry.csv", index=False)
    if prediction_history:
        pd.DataFrame(prediction_history).to_csv(results_dir / f"{id}_predictions.csv", index=False)
    if orchestrator.routing_decisions:
        import json
        with open(results_dir / f"{id}_routing_decisions.jsonl", "w") as f:
            f.writelines(json.dumps(decision) + "\n" for decision in orchestrator.routing_decisions)

    return {"status": "stopped", "experiment": id}

@app.get("/api/v1/replay/{experiment_id}")
def replay_experiment(experiment_id: str):
    raise HTTPException(status_code=501, detail="Replay not yet fully implemented")
