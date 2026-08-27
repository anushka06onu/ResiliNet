import os
import sqlite3
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.app.services.orchestrator import Orchestrator


def test_sqlite_persistence():
    orchestrator = Orchestrator()
    # Check if DB was created
    assert os.path.exists(orchestrator.db_path)
    
    # Check table
    conn = sqlite3.connect(orchestrator.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='routing_decisions';")
    assert cursor.fetchone() is not None
    conn.close()

