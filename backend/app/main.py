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
from pydantic import BaseModel, Field, field_validator
from app.config import sla_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
    from app.db.database import db_manager
    db_manager.initialize_db()
    yield
    # Shutdown
    for ws in list(manager.active_connections):
        try:
            await ws.close()
        except Exception as e:
            logging.debug(f"Error closing websocket during shutdown: {e}")
    manager.active_connections.clear()
    for exp_id in list(experiment_manager.active_processes.keys()):
        try:
            experiment_manager.stop(exp_id)
        except Exception as e:
            logging.warning(f"Error stopping experiment {exp_id} during shutdown: {e}")
    try:
        db_manager.close()
    except Exception as e:
        logging.warning(f"Error closing database during shutdown: {e}")

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
                logging.debug(f"Error broadcasting message to client: {e}")

manager = ConnectionManager()

# Global orchestrator and telemetry
from app.services.orchestrator import Orchestrator
orchestrator = Orchestrator()

# ---------------------------------------------------------
# Health Check Endpoints
# ---------------------------------------------------------
@app.get("/health/live")
def health_live():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/health/ready")
def health_ready():
    from app.api.predict import MODEL_LOADED
    from app.db.database import db_manager

    db_ok = False
    try:
        conn = db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        db_ok = cur.fetchone()[0] == 1
    except Exception as e:
        logging.error(f"Database readiness check failed: {e}")

    overall_ready = MODEL_LOADED and db_ok
    status_code = 200 if overall_ready else 503

    return {
        "status": "ready" if overall_ready else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "model_loaded": MODEL_LOADED,
            "database_connected": db_ok,
        }
    }

@app.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
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
    port_no: int = Field(ge=1)
    features: TelemetryMetrics

latest_features = {}
last_telemetry_timestamp = None

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

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

    if computed_features.get("status") == "INVALID_SAMPLE":
        return {"status": "dropped", "message": computed_features.get("message", "Invalid sample")}

    latest_features[link_id] = computed_features

    # Append to telemetry history
    tel_record = computed_features.copy()
    tel_record['timestamp'] = last_telemetry_timestamp.isoformat()
    tel_record['link_id'] = link_id
    telemetry_history.append(tel_record)

    latency_ms = computed_features.get("control_plane_rtt_ms", 0.0)
    loss_pct = computed_features.get("loss_mean_30s", 0.0)
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

    topo_path = PROJECT_ROOT / 'frontend' / 'public' / 'topology.json'
    if topo_path.exists():
        with open(topo_path, 'r') as f:
            return json.load(f)
    return {"nodes": [], "links": [], "mode": "DEMO DATA"}

@app.get("/api/v1/links/{link_id}")
def get_link_details(link_id: str):
    capacity_mbps = 10.0
    capacity_source = "topology_configuration"
    if active_live_topology:
        for link in active_live_topology.get("links", []):
            src, tgt = link.get("source"), link.get("target")
            if f"{src}-{tgt}" == link_id or f"{tgt}-{src}" == link_id:
                raw_cap = link.get("capacity", 10.0)
                if isinstance(raw_cap, str) and "mbps" in raw_cap.lower():
                    try:
                        capacity_mbps = float(raw_cap.lower().replace("mbps", "").strip())
                    except ValueError:
                        capacity_mbps = 10.0
                elif isinstance(raw_cap, (int, float)):
                    capacity_mbps = float(raw_cap)
                capacity_source = "active_topology"
                break

    features = latest_features.get(link_id, {})
    throughput_mbps = features.get("rx_bytes", 0.0) * 8 / 1_000_000 if features else 0.0
    loss_percent = features.get("loss_mean_30s", 0.0) if features else 0.0
    latency_ms = features.get("control_plane_rtt_ms", 0.0) if features else 0.0
    utilization_ratio = throughput_mbps / capacity_mbps if capacity_mbps > 0 else 0.0

    return {
        "link_id": link_id,
        "capacity_mbps": float(capacity_mbps),
        "capacity_source": capacity_source,
        "throughput_mbps": round(float(throughput_mbps), 2),
        "loss_percent": round(float(loss_percent), 2),
        "latency_ms": round(float(latency_ms), 2),
        "utilization_ratio": round(float(utilization_ratio), 4)
    }

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
            import pandas as pd
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
                    for f in explanation.get("features", []):
                        if f.get("importance") is not None:
                            val = f["importance"]
                            f["importance"] = float(val)
                except Exception as e:
                    logging.warning(f"Error computing local SHAP explanation: {e}")
                    explanation = {"status": "error", "error": str(e)}

            is_violation = prob > DECISION_THRESHOLD
            return {
                "mode": "LIVE LAB",
                "prediction_status": "available",
                "congestion_probability": round(prob, 4),
                "is_violation_predicted": is_violation,
                "confidence_score": round(abs(prob - 0.5) * 2, 4),
                "explanation": explanation
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Prediction retrieval error: {e}")
        return {
            "mode": "LIVE LAB",
            "prediction_status": "error",
            "error": str(e)
        }

    return {
        "mode": "LIVE LAB",
        "prediction_status": "unavailable",
        "congestion_probability": None,
        "is_violation_predicted": False,
        "explanation": {"status": "unavailable"}
    }

# ---------------------------------------------------------
# Flows & QoS Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/flows")
def list_flows():
    return list(orchestrator.flows.values())

@app.get("/api/v1/flows/{flow_id}")
def get_flow(flow_id: str):
    if flow_id in orchestrator.flows:
        return orchestrator.flows[flow_id]
    if flow_id == "f_mock_1":
        return {
            "flow_id": "f_mock_1",
            "tier": "Critical",
            "sla": {"max_latency_ms": 20, "max_loss_percent": 1.0},
            "metrics": {"latency_ms": None, "loss_percent": None, "status": "unavailable"}
        }
    raise HTTPException(status_code=404, detail="Flow not found")

# ---------------------------------------------------------
# Routing Decisions Endpoints
# ---------------------------------------------------------
from fastapi import Query

@app.get("/api/v1/routing/decisions")
def list_routing_decisions(
    experiment_id: Optional[str] = None,
    flow_id: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    from app.db.database import db_manager
    try:
        items = db_manager.query_decisions(
            experiment_id=experiment_id,
            flow_id=flow_id,
            outcome=outcome,
            limit=limit,
            offset=offset
        )
        total = db_manager.count_decisions(
            experiment_id=experiment_id,
            flow_id=flow_id,
            outcome=outcome
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total
        }
    except Exception as e:
        logging.error(f"Error reading routing decisions from DB: {e}")
        res = orchestrator.routing_decisions
        if experiment_id:
            res = [d for d in res if d.get("experiment_id") == experiment_id]
        if flow_id:
            res = [d for d in res if d.get("flow_id") == flow_id]
        if outcome:
            res = [d for d in res if d.get("outcome_status") == outcome]
        total = len(res)
        items = res[offset:offset+limit]
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total
        }

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

        experiment_script = PROJECT_ROOT / "experiments" / "run_experiment.py"
        cmd = [
            "python3", str(experiment_script),
            "--scenario", config.scenario,
            "--duration", str(config.duration),
            "--seed", str(config.seed),
            "--experiment-id", id,
            "--policy", config.policy,
            "--require-sync"
        ]
        proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
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
                manifest_path = PROJECT_ROOT / "experiments" / "results" / id / "manifest.json"
                if not manifest_path.exists():
                    manifest_path = PROJECT_ROOT / "experiments" / "results" / f"{id}_manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r") as f:
                            man = json.load(f)
                            self.historical_records[id]["status"] = man.get("status", "completed" if code == 0 else f"failed (code {code})")
                    except Exception as e:
                        logging.warning(f"Error reading manifest: {e}")
                        self.historical_records[id]["status"] = "completed" if code == 0 else f"failed (code {code})"
                else:
                    self.historical_records[id]["status"] = "completed" if code == 0 else f"failed (code {code})"
                del self.active_processes[id]
                return self.historical_records[id]["status"]

        if id in self.historical_records:
            return self.historical_records[id]["status"]

        manifest_path = PROJECT_ROOT / "experiments" / "results" / id / "manifest.json"
        if not manifest_path.exists():
            manifest_path = PROJECT_ROOT / "experiments" / "results" / f"{id}_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r") as f:
                    man = json.load(f)
                    return man.get("status", "completed")
            except Exception as e:
                logging.warning(f"Error parsing manifest {manifest_path}: {e}")

        return "unknown"

experiment_manager = ExperimentManager()

@app.get("/api/v1/experiments/scenarios")
def list_scenarios():
    return ["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"]

@app.get("/api/v1/experiments")
def list_experiments(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    results = {}

    # Add finished from results directory (isolated directory structure first)
    results_dir = PROJECT_ROOT / "experiments" / "results"
    if results_dir.exists():
        for manifest_path in sorted(results_dir.glob("*/manifest.json")):
            try:
                with manifest_path.open("r", encoding="utf-8") as file:
                    manifest = json.load(file)

                exp_id = manifest.get("experiment_id") or manifest_path.parent.name
                if exp_id:
                    results[exp_id] = {
                        "id": exp_id,
                        "status": manifest.get("status", "unknown"),
                        "scenario": manifest.get("scenario"),
                        "seed": manifest.get("seed"),
                        "policy": manifest.get("effective_policy") or manifest.get("requested_policy") or manifest.get("policy"),
                    }
            except Exception as e:
                logging.warning(f"Failed to read manifest {manifest_path}: {e}")

        # Also support legacy flat format
        for manifest_path in sorted(results_dir.glob("*_manifest.json")):
            try:
                with manifest_path.open("r", encoding="utf-8") as file:
                    manifest = json.load(file)

                exp_id = manifest.get("experiment_id")
                if exp_id and exp_id not in results:
                    results[exp_id] = {
                        "id": exp_id,
                        "status": manifest.get("status", "unknown"),
                        "scenario": manifest.get("scenario"),
                        "seed": manifest.get("seed"),
                        "policy": manifest.get("policy"),
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

    exp_list = list(results.values())
    if status:
        exp_list = [e for e in exp_list if e.get("status") == status]
    total = len(exp_list)
    items = exp_list[offset:offset+limit]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total
    }

@app.get("/api/v1/experiments/{id}")
def get_experiment(id: str):
    status = experiment_manager.status(id)
    if status == "unknown":
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"id": id, "status": status}


class ExperimentConfig(BaseModel):
    scenario: Literal["normal", "gradual_congestion", "sudden_surge", "concurrent_flows"] = "normal"
    duration: int = Field(60, ge=10, le=3600)
    seed: int = 42
    policy: str = "predictive"

    @field_validator("policy")
    def validate_policy(cls, v):
        from network.routing.policies import normalize_policy
        return normalize_policy(v)


class ExperimentConfigureRequest(BaseModel):
    policy: str

    @field_validator("policy")
    def validate_policy(cls, v):
        from network.routing.policies import normalize_policy
        return normalize_policy(v)


telemetry_history = []
prediction_history = []

INTERNAL_API_TOKEN = os.environ.get("RESILINET_INTERNAL_TOKEN", "resilinet-internal-secret-token")

from fastapi import Depends, Header

def verify_internal_token(x_resilinet_internal_token: Optional[str] = Header(None)):
    if x_resilinet_internal_token != INTERNAL_API_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing internal token")

import re

@app.post("/api/v1/internal/experiments/{id}/configure", dependencies=[Depends(verify_internal_token)])
def internal_configure_experiment(id: str, req: ExperimentConfigureRequest):
    """Internal endpoint for runner to configure orchestrator context and verify policy."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", id):
        raise HTTPException(status_code=422, detail="Invalid experiment ID")
    orchestrator.begin_experiment(id, req.policy)
    return {
        "experiment_id": id,
        "requested_policy": req.policy,
        "effective_policy": orchestrator.policy,
        "status": "CONFIGURED"
    }

@app.post("/api/v1/internal/experiments/{id}/finalize", dependencies=[Depends(verify_internal_token)])
def internal_finalize_experiment(id: str):
    """Internal endpoint to export in-memory records into the isolated experiment directory."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", id):
        raise HTTPException(status_code=422, detail="Invalid experiment ID")
    if orchestrator.active_experiment_id != id:
        raise HTTPException(status_code=409, detail=f"Experiment context mismatch: active={orchestrator.active_experiment_id}, requested={id}")

    run_dir = PROJECT_ROOT / "experiments" / "results" / id
    run_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    if telemetry_history:
        pd.DataFrame(telemetry_history).to_csv(run_dir / "telemetry.csv", index=False)
    if prediction_history:
        pd.DataFrame(prediction_history).to_csv(run_dir / "predictions.csv", index=False)
    if orchestrator.routing_decisions:
        with open(run_dir / "routing_decisions.jsonl", "w") as f:
            f.writelines(json.dumps(decision) + "\n" for decision in orchestrator.routing_decisions)
    return {"status": "FINALIZED", "experiment_id": id}

@app.post("/api/v1/experiments/{id}/start")
def start_experiment(id: str, config: ExperimentConfig = None):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", id):
        raise HTTPException(status_code=422, detail="Invalid experiment ID")

    # Enforce exactly one active experiment
    active_running = [eid for eid, proc in experiment_manager.active_processes.items() if proc.poll() is None]
    if active_running:
        raise HTTPException(status_code=409, detail=f"Another experiment is currently running: {active_running[0]}")

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
        manifest_path = PROJECT_ROOT / "experiments" / "results" / id / "manifest.json"
        if not manifest_path.exists():
            manifest_path = PROJECT_ROOT / "experiments" / "results" / f"{id}_manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="Experiment not found")

    experiment_manager.stop(id)

    # Dump artifacts to isolated directory
    import pandas as pd
    run_dir = PROJECT_ROOT / 'experiments' / 'results' / id
    run_dir.mkdir(parents=True, exist_ok=True)

    if telemetry_history:
        pd.DataFrame(telemetry_history).to_csv(run_dir / "telemetry.csv", index=False)
    if prediction_history:
        pd.DataFrame(prediction_history).to_csv(run_dir / "predictions.csv", index=False)
    if orchestrator.routing_decisions:
        with open(run_dir / "routing_decisions.jsonl", "w") as f:
            f.writelines(json.dumps(decision) + "\n" for decision in orchestrator.routing_decisions)

    return {"status": "stopped", "experiment": id}

@app.get("/api/v1/telemetry/history")
def get_telemetry_history(
    switch_id: Optional[str] = None,
    port_no: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    global telemetry_history
    records = telemetry_history
    if switch_id:
        records = [r for r in records if r.get("switch_id") == switch_id]
    if port_no is not None:
        records = [r for r in records if r.get("port_no") == port_no or str(r.get("port_no")) == str(port_no)]
    total = len(records)
    items = records[offset:offset+limit]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total
    }

@app.get("/api/v1/predictions/history")
def get_predictions_history(
    switch_id: Optional[str] = None,
    port_no: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    global prediction_history
    records = prediction_history
    if switch_id:
        records = [r for r in records if r.get("switch_id") == switch_id]
    if port_no is not None:
        records = [r for r in records if r.get("port_no") == port_no or str(r.get("port_no")) == str(port_no)]
    total = len(records)
    items = records[offset:offset+limit]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total
    }

@app.get("/api/v1/replay/{experiment_id}")
def replay_experiment(experiment_id: str):
    raise HTTPException(status_code=501, detail="Replay not yet fully implemented")
