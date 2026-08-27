import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.config import sla_config

project_root = Path(__file__).resolve().parents[2]

# Import routers
try:
    from app.api.predict import router as predict_router
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from api.predict import router as predict_router

class TopologyNode(BaseModel):
    id: str
    type: str

class TopologyLink(BaseModel):
    source: str
    source_port: int | None = None
    target: str
    target_port: int | None = None
    capacity: str | None = None

class TopologySchema(BaseModel):
    nodes: List[TopologyNode]
    links: List[TopologyLink]
    mode: Optional[str] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.services.orchestrator import orchestrator
    orchestrator.initialize_db()
    yield
    # Shutdown
    for ws in list(manager.active_connections):
        try:
            await ws.close()
        except Exception:
            pass
    manager.active_connections.clear()
    for exp_id in list(experiment_manager.active_processes.keys()):
        try:
            experiment_manager.stop(exp_id)
        except Exception:
            pass
    try:
        if hasattr(orchestrator, 'conn') and orchestrator.conn:
            orchestrator.conn.close()
    except Exception:
        pass

app = FastAPI(
    title="ResiliNet API",
    description="Network Digital Twin Backend for Predictive QoS and Routing",
    version="1.1.0",
    lifespan=lifespan
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
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
        failed = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logging.warning(f"WebSocket broadcast error: {e}")
                failed.append(connection)
        for connection in failed:
            self.disconnect(connection)

manager = ConnectionManager()

@app.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"WS Client says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

class TelemetryMetrics(BaseModel):
    rx_bytes: float = Field(ge=0, allow_inf_nan=False)
    tx_bytes: float = Field(ge=0, allow_inf_nan=False)
    control_plane_rtt_ms: float = Field(ge=0, allow_inf_nan=False)
    tx_dropped: float = Field(ge=0, allow_inf_nan=False)
    loss_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    utilization: float = Field(ge=0, le=1, allow_inf_nan=False)

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
    last_telemetry_timestamp = datetime.now(timezone.utc)

    link_id = f"{payload.switch_id}-p{payload.port_no}"

    computed_features = feature_pipeline.process_raw_telemetry(
        link_id=link_id,
        raw_metrics=payload.features.model_dump(),
        timestamp=last_telemetry_timestamp
    )

    if computed_features.get("status") == "INSUFFICIENT_DATA":
        latest_features[link_id] = payload.features.model_dump()
        return {"status": "warming_up", "message": "Gathering more telemetry"}

    if computed_features.get("status") == "STALE_DATA":
        return {"status": "dropped", "message": "Stale metric"}

    latest_features[link_id] = computed_features

    # Append to telemetry history
    tel_record = computed_features.copy()
    tel_record['timestamp'] = last_telemetry_timestamp.isoformat()
    tel_record['link_id'] = link_id
    telemetry_history.append(tel_record)

    latency_ms = computed_features.get("control_plane_rtt_ms", 0.0)
    loss_pct = computed_features.get("loss_percent", 0.0)
    is_violation_actual = (
        latency_ms > sla_config.max_latency_ms
        or loss_pct > sla_config.max_loss_percent
    )

    event = {
        "mode": "LIVE LAB",
        "source": "mininet_ryu",
        "type": "link_telemetry",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
            project_root_str = str(Path(__file__).resolve().parents[2])
            if project_root_str not in sys.path:
                sys.path.append(project_root_str)
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

                pred_record = computed_features.copy()
                pred_record['timestamp'] = event["timestamp"]
                pred_record['link_id'] = link_id
                pred_record['predicted_risk'] = float(prob)
                prediction_history.append(pred_record)
            except Exception as e:
                logging.error(f"Prediction failed: {e}")
                event["payload"]["prediction_status"] = "inference_failed"
        else:
            event["payload"]["prediction_status"] = "model_unavailable"
    except Exception as e:
        event["payload"]["prediction_status"] = "inference_failed"
        logging.error(f"Prediction exception: {e}")

    # Pass the event to the Orchestrator to evaluate flows and routing
    asyncio.create_task(asyncio.to_thread(orchestrator.handle_telemetry_event, event))

    await manager.broadcast(event)
    return {"status": "ingested"}

# ---------------------------------------------------------
# System & Topology Endpoints
# ---------------------------------------------------------
active_live_topology = None

from app.services.orchestrator import orchestrator

@app.post("/api/v1/topology/ingest")
async def ingest_topology(payload: TopologySchema):
    global active_live_topology
    active_live_topology = payload.model_dump()
    orchestrator.load_topology(active_live_topology)
    return {"status": "topology_ingested"}

@app.get("/api/v1/system/status")
def system_status():
    if not last_telemetry_timestamp:
        mode = "NO_DATA"
    else:
        dt = (datetime.now(timezone.utc) - last_telemetry_timestamp).total_seconds()
        if dt <= 10.0:
            mode = "LIVE"
        else:
            mode = "STALE"

    return {"status": mode, "version": "1.1.0", "active_connections": len(manager.active_connections)}

@app.get("/api/v1/topologies")
def list_topologies():
    return ["small_test", "sndlib_campus", "sndlib_backbone"]

@app.get("/api/v1/topology/current")
def get_current_topology():
    if active_live_topology is not None:
        return active_live_topology

    topo_path = project_root / 'frontend' / 'public' / 'topology.json'
    if topo_path.exists():
        with open(topo_path, 'r') as f:
            return json.load(f)
    return {"nodes": [], "links": [], "mode": "DEMO DATA"}

@app.get("/api/v1/links/{link_id}")
def get_link_details(link_id: str):
    capacity = "10Mbps"
    if active_live_topology:
        for link in active_live_topology.get("links", []):
            src, tgt = link.get("source"), link.get("target")
            if f"{src}-{tgt}" == link_id or f"{tgt}-{src}" == link_id:
                capacity = link.get("capacity", "10Mbps")
                break
    
    features = latest_features.get(link_id, {})
    # Assuming rx_bytes is bytes per second, convert to Mbps
    throughput = features.get("rx_bytes", 0) * 8 / 1_000_000 if features else 0.0
    return {"link_id": link_id, "capacity": capacity, "current_throughput": f"{throughput:.2f} Mbps"}

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
    except HTTPException:
        raise
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
def list_routing_decisions(
    experiment_id: Optional[str] = None,
    flow_id: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    try:
        with orchestrator.db_lock:
            cursor = orchestrator.conn.cursor()
            query = """
                SELECT decision_id, experiment_id, flow_id, timestamp, risk_before, risk_after,
                       original_path, proposed_path, safeguard_result, installation_status,
                       verification_status, outcome_status, failure_stage, error_type, rollback_result
                FROM routing_decisions
                WHERE 1=1
            """
            params = []
            if experiment_id:
                query += " AND experiment_id = ?"
                params.append(experiment_id)
            if flow_id:
                query += " AND flow_id = ?"
                params.append(flow_id)
            if outcome:
                query += " AND outcome_status = ?"
                params.append(outcome)
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            decisions = []
            for r in rows:
                decisions.append({
                    "decision_id": r[0],
                    "experiment_id": r[1],
                    "flow_id": r[2],
                    "timestamp": r[3],
                    "risk_before": r[4],
                    "risk_after": r[5],
                    "original_path": json.loads(r[6]) if r[6] else None,
                    "proposed_path": json.loads(r[7]) if r[7] else None,
                    "safeguard_result": r[8],
                    "installation_status": r[9],
                    "verification_status": r[10],
                    "outcome_status": r[11],
                    "failure_stage": r[12],
                    "error_type": r[13],
                    "rollback_result": r[14]
                })
            return decisions
    except Exception as e:
        logging.error(f"Error reading routing decisions from DB: {e}")
        res = orchestrator.routing_decisions
        if experiment_id:
            res = [d for d in res if d.get("experiment_id") == experiment_id]
        if flow_id:
            res = [d for d in res if d.get("flow_id") == flow_id]
        if outcome:
            res = [d for d in res if d.get("outcome_status") == outcome]
        return res[offset:offset+limit]

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
        if id not in self.active_processes and id not in self.historical_records:
            return False

        if id in self.active_processes:
            proc = self.active_processes[id]
            if proc.poll() is None:
                import signal
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            del self.active_processes[id]

        if id in self.historical_records:
            self.historical_records[id]["status"] = "STOPPED"
        return True

    def status(self, id: str):
        if id in self.active_processes:
            proc = self.active_processes[id]
            if proc.poll() is None:
                return "running"
            else:
                code = proc.returncode
                manifest_path = Path(project_root) / "experiments" / "results" / f"{id}_manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r") as f:
                            man = json.load(f)
                            self.historical_records[id]["status"] = man.get("status", "completed" if code == 0 else f"failed (code {code})")
                    except Exception:
                        self.historical_records[id]["status"] = "completed" if code == 0 else f"failed (code {code})"
                else:
                    self.historical_records[id]["status"] = "completed" if code == 0 else f"failed (code {code})"
                del self.active_processes[id]
                return self.historical_records[id]["status"]

        if id in self.historical_records:
            return self.historical_records[id]["status"]

        manifest_path = Path(project_root) / "experiments" / "results" / f"{id}_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r") as f:
                    man = json.load(f)
                    return man.get("status", "completed")
            except Exception:
                pass

        return "unknown"

experiment_manager = ExperimentManager()

@app.get("/api/v1/experiments")
def list_experiments():
    results = {}

    # Add finished from results directory
    results_dir = Path(project_root) / "experiments" / "results"
    if results_dir.exists():
        for manifest_path in results_dir.glob("*_manifest.json"):
            try:
                with manifest_path.open("r", encoding="utf-8") as file:
                    manifest = json.load(file)

                exp_id = manifest.get("experiment_id")
                if exp_id:
                    results[exp_id] = {
                        "id": exp_id,
                        "status": manifest.get("status", "unknown"),
                        "scenario": manifest.get("scenario"),
                        "seed": manifest.get("seed"),
                    }
            except Exception as e:
                logging.warning(f"Failed to read manifest {manifest_path}: {e}")

    # Add currently active (overriding/taking priority)
    for exp_id, proc in experiment_manager.active_processes.items():
        if proc.poll() is None:
            results[exp_id] = {
                "id": exp_id,
                "status": "running"
            }

    return list(results.values())

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
    raise HTTPException(status_code=501, detail="Pause not supported directly in Mininet yet")

@app.post("/api/v1/experiments/{id}/stop")
def stop_experiment(id: str):
    if id not in experiment_manager.active_processes and id not in experiment_manager.historical_records:
        manifest_path = Path(project_root) / "experiments" / "results" / f"{id}_manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="Experiment not found")

    experiment_manager.stop(id)

    # Dump artifacts
    import pandas as pd
    results_dir = Path(project_root) / 'experiments' / 'results'
    os.makedirs(results_dir, exist_ok=True)

    if telemetry_history:
        pd.DataFrame(telemetry_history).to_csv(results_dir / f"{id}_telemetry.csv", index=False)
    if prediction_history:
        pd.DataFrame(prediction_history).to_csv(results_dir / f"{id}_predictions.csv", index=False)
    if orchestrator.routing_decisions:
        with open(results_dir / f"{id}_routing_decisions.jsonl", "w") as f:
            f.writelines(json.dumps(decision) + "\n" for decision in orchestrator.routing_decisions)

    return {"status": "stopped", "experiment": id}

@app.get("/api/v1/replay/{experiment_id}")
def replay_experiment(experiment_id: str):
    raise HTTPException(status_code=501, detail="Replay not yet fully implemented")
