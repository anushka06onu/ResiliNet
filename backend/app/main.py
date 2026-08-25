from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import json

app = FastAPI(
    title="ResiliNet API",
    description="Network Digital Twin Backend for Predictive QoS and Routing",
    version="1.0.0"
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/ready")
def readiness_check():
    return {"status": "ready"}

@app.get("/api/v1/topology")
def get_topology():
    """Return the topology graph. For now, read the generated JSON if it exists."""
    # This assumes backend is run from the project root.
    topo_path = 'frontend/public/topology.json'
    if os.path.exists(topo_path):
        with open(topo_path, 'r') as f:
            return json.load(f)
    return {"error": "Topology file not found. Ensure campus_health.py has run."}
