from pathlib import Path
from app.db.database import DatabaseManager

def test_database_manager(tmp_path):
    test_db = tmp_path / "test_resilinet.db"
    db = DatabaseManager(db_path=test_db)
    db.initialize_db()

    decision = {
        "decision_id": "dec-101",
        "experiment_id": "exp-001",
        "flow_id": "f_1",
        "timestamp": "2026-08-27T12:00:00Z",
        "risk_before": 0.8,
        "risk_after": 0.1,
        "original_path": ["s1", "s2"],
        "proposed_path": ["s1", "s3", "s2"],
        "safeguard_result": "OK",
        "installation_status": "success",
        "verification_status": "success",
        "outcome_status": "success",
        "failure_stage": None,
        "error_type": None,
        "rollback_result": None
    }

    db.record_decision(decision)

    # Query with filters
    results = db.query_decisions(experiment_id="exp-001")
    assert len(results) == 1
    assert results[0]["decision_id"] == "dec-101"
    assert results[0]["proposed_path"] == ["s1", "s3", "s2"]

    # Filter with non-matching outcome
    empty_results = db.query_decisions(outcome="failed")
    assert len(empty_results) == 0

    db.close()
