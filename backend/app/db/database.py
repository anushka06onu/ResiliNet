import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any

project_root = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = project_root / 'experiments' / 'results' / 'resilinet.db'

class DatabaseManager:
    """
    Dedicated database persistence layer for ResiliNet.
    Handles schema migrations, thread-safe connection management, and decision queries.
    """
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return self._conn

    def initialize_db(self):
        """Run migrations and create tables if they do not exist."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.cursor()
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
                    outcome_status TEXT,
                    failure_stage TEXT,
                    error_type TEXT,
                    rollback_result TEXT
                )
            ''')
            # Create indexes for fast querying by experiment and flow
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_decisions_exp ON routing_decisions(experiment_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_decisions_flow ON routing_decisions(flow_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_decisions_ts ON routing_decisions(timestamp)')
            conn.commit()
            logging.info("Database schema initialized and indexed successfully.")

    def record_decision(self, decision: Dict[str, Any]):
        """Persist a routing decision record."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO routing_decisions (
                    decision_id, experiment_id, flow_id, timestamp, risk_before, risk_after,
                    original_path, proposed_path, safeguard_result, installation_status,
                    verification_status, outcome_status, failure_stage, error_type, rollback_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                decision["decision_id"],
                decision["experiment_id"],
                decision["flow_id"],
                decision["timestamp"],
                decision["risk_before"],
                decision["risk_after"],
                json.dumps(decision["original_path"]) if decision.get("original_path") else None,
                json.dumps(decision["proposed_path"]) if decision.get("proposed_path") else None,
                decision.get("safeguard_result"),
                decision.get("installation_status"),
                decision.get("verification_status"),
                decision.get("outcome_status"),
                decision.get("failure_stage"),
                decision.get("error_type"),
                decision.get("rollback_result")
            ))
            conn.commit()

    def query_decisions(
        self,
        experiment_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve persisted decisions with optional filters."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.cursor()
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
            query += " ORDER BY timestamp DESC, decision_id DESC LIMIT ? OFFSET ?"
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

    def count_decisions(
        self,
        experiment_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        outcome: Optional[str] = None
    ) -> int:
        """Count total decisions matching query filters."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) FROM routing_decisions WHERE 1=1"
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
            cursor.execute(query, params)
            row = cursor.fetchone()
            return row[0] if row else 0

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

db_manager = DatabaseManager()
