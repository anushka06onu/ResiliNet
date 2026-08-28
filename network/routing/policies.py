"""
Centralized routing policy definitions, aliases, and normalization for ResiliNet.
"""

POLICY_MAP = {
    # Baseline: Fixed shortest paths with zero dynamic rerouting
    "static": "static",
    "no_reroute": "static",
    # Reactive: Dynamic rerouting only after actual SLA violation is detected
    "reactive": "reactive",
    "reactive_threshold": "reactive",
    # Predictive: Proactive ML-driven rerouting before physical violation occurs
    "predictive": "predictive",
    "predictive_ml": "predictive",
}

CANONICAL_POLICIES = ["static", "reactive", "predictive"]

SCIENTIFIC_LABELS = {
    "static": "no_reroute",
    "reactive": "reactive_threshold",
    "predictive": "predictive_ml"
}


def normalize_policy(policy: str) -> str:
    """
    Normalizes any accepted policy alias to its canonical representation ('static', 'reactive', 'predictive').
    Raises ValueError on unrecognized policies.
    """
    if not isinstance(policy, str):
        raise ValueError(f"Policy must be a string, got {type(policy)}")
    
    clean = policy.strip().lower()
    if clean in POLICY_MAP:
        return POLICY_MAP[clean]
    
    raise ValueError(f"Invalid routing policy '{policy}'. Allowed options: {sorted(list(POLICY_MAP.keys()))}")


def get_scientific_label(policy: str) -> str:
    """Returns the scientific research descriptor for the policy."""
    canonical = normalize_policy(policy)
    return SCIENTIFIC_LABELS[canonical]
