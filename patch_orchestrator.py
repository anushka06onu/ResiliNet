import sys

filename = "backend/app/services/orchestrator.py"
with open(filename, "r") as f:
    content = f.read()

# Add sqlite setup and policy to init
init_patch = """
        self.router = PredictiveRouter(topology_json=str(topology_path))
        self.flows = {}
        self.flow_locks = {}
        self.routing_decisions = []
        self.policy = "predictive"
        
        # SQLite Persistence
        import sqlite3
        self.db_path = project_root / 'experiments' / 'results' / 'resilinet.db'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS routing_decisions (
                decision_id TEXT PRIMARY KEY,
                experiment_id TEXT,
                flow_id TEXT,
                timestamp TEXT,
                risk_before REAL,
                risk_after REAL,
                original_path TEXT,
                proposed_path TEXT,
                safeguard_result TEXT,
                installation_status TEXT,
                verification_status TEXT,
                outcome_status TEXT
            )
        ''')
        self.conn.commit()
        
    def set_policy(self, policy: str):
        self.policy = policy
        logging.info(f"Orchestrator policy set to: {self.policy}")
"""
content = content.replace(
"""        self.router = PredictiveRouter(topology_json=str(topology_path))
        self.flows = {}
        self.flow_locks = {}
        self.routing_decisions = []""", init_patch)


# Handle telemetry event - policy handling
telemetry_patch = """
                if edge_found and target_switch:
                    is_violation_actual = event.get("payload", {}).get("is_violation_actual", False)
                    evaluate = False
                    
                    if self.policy == "predictive" and is_violation:
                        evaluate = True
                    elif self.policy == "reactive" and is_violation_actual:
                        evaluate = True
                        
                    if evaluate:
                        self._evaluate_affected_flows(switch, target_switch)
"""

content = content.replace(
"""                if edge_found and is_violation and target_switch:
                    self._evaluate_affected_flows(switch, target_switch)""", telemetry_patch)

# SQLite insertion
sqlite_patch = """
                        self.routing_decisions.append(decision)
                        
                        # Persist to SQLite
                        import json
                        try:
                            cursor = self.conn.cursor()
                            cursor.execute('''
                                INSERT INTO routing_decisions (
                                    decision_id, experiment_id, flow_id, timestamp, risk_before, risk_after,
                                    original_path, proposed_path, safeguard_result, installation_status,
                                    verification_status, outcome_status
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                decision["decision_id"], decision["experiment_id"], decision["flow_id"],
                                decision["timestamp"], decision["risk_before"], decision["risk_after"],
                                json.dumps(decision["original_path"]), 
                                json.dumps(decision["proposed_path"]) if decision["proposed_path"] else None,
                                decision["safeguard_result"], decision["installation_status"],
                                decision["verification_status"], decision["outcome_status"]
                            ))
                            self.conn.commit()
                        except Exception as e:
                            logging.error(f"Failed to persist decision to SQLite: {e}")
                finally:
"""

content = content.replace(
"""                        self.routing_decisions.append(decision)
                finally:""", sqlite_patch)

with open(filename, "w") as f:
    f.write(content)
