from pydantic import BaseModel

class SLAPolicy(BaseModel):
    max_latency_ms: float = 20.0
    max_loss_percent: float = 1.0
    max_control_plane_rtt_ms: float = 50.0

sla_config = SLAPolicy()
