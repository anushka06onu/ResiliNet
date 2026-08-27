import sys

filename = "frontend/src/services/api.ts"
with open(filename, "r") as f:
    content = f.read()

patch = """
export const getFlows = async () => {
  try {
    if (isSimulationMode) throw new Error('Force mock');
    const res = await fetch(`${API_BASE}/flows`);
    if (!res.ok) throw new Error('Network response was not ok');
    return await res.json();
  } catch {
    return [
      { id: 'f_001', src: 'h1', dst: 'server1', category: 'Telemedicine', tier: 'Critical', current_path: ['s1','s3','s7'], latency: '12.4ms', loss: '0.0%', sla_status: 'Healthy', risk: '12%' },
      { id: 'f_002', src: 'h2', dst: 'server2', category: 'Education', tier: 'Video', current_path: ['s2','s4','s8'], latency: '34.1ms', loss: '0.1%', sla_status: 'At-Risk', risk: '65%' },
      { id: 'f_003', src: 'h3', dst: 'server1', category: 'Background', tier: 'Bulk', current_path: ['s5','s6','s7'], latency: '120.5ms', loss: '2.4%', sla_status: 'Violated', risk: '98%' },
    ];
  }
};

export const getRoutingDecisions = async () => {
  try {
    if (isSimulationMode) throw new Error('Force mock');
    const res = await fetch(`${API_BASE}/routing/decisions`);
    if (!res.ok) throw new Error('Network response was not ok');
    return await res.json();
  } catch {
    return [
      {
        decision_id: "demo-1",
        flow_id: "f_001",
        timestamp: new Date().toISOString(),
        risk_before: 0.85,
        risk_after: 0.24,
        original_path: ["s1", "s2", "s4"],
        proposed_path: ["s1", "s3", "s4"],
        installation_status: "success",
        safeguard_result: "Link s2-s4 Risk 85%"
      },
      {
        decision_id: "demo-2",
        flow_id: "f_002",
        timestamp: new Date(Date.now() - 300000).toISOString(),
        risk_before: 0.92,
        risk_after: null,
        original_path: ["s2", "s5", "s8"],
        proposed_path: ["s2", "s6", "s8"],
        installation_status: "failed",
        safeguard_result: "Verification failed, triggered rollback"
      }
    ];
  }
};

export const startExperiment = async (config: any) => {
  const exp_id = `exp_${config.policy}_${config.scenario}_ui`;
  const res = await fetch(`${API_BASE}/experiments/${exp_id}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
  if (!res.ok) throw new Error('Failed to start experiment');
  return await res.json();
};

export const stopExperiment = async (exp_id: string) => {
  const res = await fetch(`${API_BASE}/experiments/${exp_id}/stop`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to stop experiment');
  return await res.json();
};

export const getExperiments = async () => {
  const res = await fetch(`${API_BASE}/experiments`);
  if (!res.ok) throw new Error('Failed to fetch experiments');
  return await res.json();
};
"""

content += "\n" + patch

with open(filename, "w") as f:
    f.write(content)
