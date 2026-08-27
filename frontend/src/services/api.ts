const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

// Global state to track if we are in live mode or simulation mode
export let isSimulationMode = false;

export interface ExperimentConfig {
  scenario: 'normal' | 'gradual_congestion' | 'sudden_surge';
  duration: number;
  seed: number;
  policy: 'static' | 'reactive' | 'predictive';
}

export interface RoutingResult {
  decision_id: string;
  experiment_id?: string;
  flow_id: string;
  timestamp: string;
  risk_before: number | null;
  risk_after: number | null;
  original_path: string[];
  proposed_path: string[] | null;
  safeguard_result: string;
  installation_status: string;
  verification_status: string;
  outcome_status: string;
}

// Mock data matching Phase 3 topology
const MOCK_TOPOLOGY = {
  nodes: [
    { id: 'core1', type: 'switch' },
    { id: 'core2', type: 'switch' },
    { id: 'dist1', type: 'switch' },
    { id: 'dist2', type: 'switch' },
    { id: 'acc1', type: 'switch' },
    { id: 'acc2', type: 'switch' },
    { id: 'h1', type: 'host' },
    { id: 'h2', type: 'host' },
    { id: 'server1', type: 'host' },
  ],
  links: [
    { source: 'core1', source_port: '1', target: 'core2', target_port: '1' },
    { source: 'core1', source_port: '2', target: 'dist1', target_port: '1' },
    { source: 'core2', source_port: '2', target: 'dist2', target_port: '1' },
    { source: 'dist1', source_port: '2', target: 'acc1', target_port: '1' },
    { source: 'dist2', source_port: '2', target: 'acc2', target_port: '1' },
    { source: 'acc1', source_port: '2', target: 'h1', target_port: '1' },
    { source: 'acc2', source_port: '2', target: 'h2', target_port: '1' },
    { source: 'core1', source_port: '3', target: 'server1', target_port: '1' },
  ],
};

export const getTopology = async () => {
  try {
    const res = await fetch(`${API_BASE}/topology/current`);
    if (!res.ok) throw new Error('Network response was not ok');
    isSimulationMode = false;
    return await res.json();
  } catch {
    console.warn('Backend unreachable, falling back to Simulation Mode for Topology.');
    isSimulationMode = true;
    return MOCK_TOPOLOGY;
  }
};

export const getPredictionAndExplanation = async (switchId: string, portNo: string) => {
  try {
    if (isSimulationMode) throw new Error('Force mock'); // Skip fetch if we are in DEMO DATA mode

    const linkId = `${switchId}-p${portNo}`;
    const res = await fetch(`${API_BASE}/links/${encodeURIComponent(linkId)}/latest-prediction`, {
      method: 'GET',
    });

    if (!res.ok) throw new Error('Network response was not ok');

    const data = await res.json();
    return data;
  } catch {
    // Realistic Mock Data for Simulation Mode (DEMO DATA)
    return new Promise((resolve) => {
      setTimeout(() => {
        const cycle = (Date.now() % 80000) / 1000;
        let prob = 0.1;
        let loss = 0.1;

        if (cycle > 60) {
          prob = 0.2; // Reroute and recovery
          loss = 0.5;
        } else if (cycle > 40) {
          prob = 0.88; // Predicted violation
          loss = 45.2;
        } else if (cycle > 20) {
          prob = 0.45; // Increasing risk
          loss = 12.5;
        }

        resolve({
          predict: {
            congestion_probability: prob,
            is_violation_predicted: prob > 0.5,
          },
          explain: {
            base_value: 0.1,
            features: [
              { name: 'loss_mean_30s', value: loss, shap_contribution: prob - 0.1 },
              { name: 'tx_bytes_rate', value: 1048576, shap_contribution: 0.2 },
              { name: 'rx_bytes_slope', value: -500, shap_contribution: -0.05 },
              {
                name: 'tx_dropped_max',
                value: prob > 0.5 ? 100 : 0,
                shap_contribution: prob > 0.5 ? 0.15 : -0.02,
              },
            ],
          },
        });
      }, 400); // simulate network latency
    });
  }
};

export const getFlows = async () => {
  try {
    if (isSimulationMode) throw new Error('Force mock');
    const res = await fetch(`${API_BASE}/flows`);
    if (!res.ok) throw new Error('Network response was not ok');
    return await res.json();
  } catch {
    return [
      {
        id: 'f_001',
        src: 'h1',
        dst: 'server1',
        category: 'Telemedicine',
        tier: 'Critical',
        current_path: ['s1', 's3', 's7'],
        latency: '12.4ms',
        loss: '0.0%',
        sla_status: 'Healthy',
        risk: '12%',
      },
      {
        id: 'f_002',
        src: 'h2',
        dst: 'server2',
        category: 'Education',
        tier: 'Video',
        current_path: ['s2', 's4', 's8'],
        latency: '34.1ms',
        loss: '0.1%',
        sla_status: 'At-Risk',
        risk: '65%',
      },
      {
        id: 'f_003',
        src: 'h3',
        dst: 'server1',
        category: 'Background',
        tier: 'Bulk',
        current_path: ['s5', 's6', 's7'],
        latency: '120.5ms',
        loss: '2.4%',
        sla_status: 'Violated',
        risk: '98%',
      },
    ];
  }
};

export const getRoutingDecisions = async (): Promise<RoutingResult[]> => {
  try {
    if (isSimulationMode) throw new Error('Force mock');
    const res = await fetch(`${API_BASE}/routing/decisions`);
    if (!res.ok) throw new Error('Network response was not ok');
    return await res.json();
  } catch {
    return [
      {
        decision_id: 'demo-1',
        flow_id: 'f_001',
        timestamp: new Date().toISOString(),
        risk_before: 0.85,
        risk_after: 0.24,
        original_path: ['s1', 's2', 's4'],
        proposed_path: ['s1', 's3', 's4'],
        installation_status: 'success',
        verification_status: 'success',
        outcome_status: 'success',
        safeguard_result: 'Link s2-s4 Risk 85%',
      },
      {
        decision_id: 'demo-2',
        flow_id: 'f_002',
        timestamp: new Date(Date.now() - 300000).toISOString(),
        risk_before: 0.92,
        risk_after: null,
        original_path: ['s2', 's5', 's8'],
        proposed_path: ['s2', 's6', 's8'],
        installation_status: 'failed',
        verification_status: 'failed',
        outcome_status: 'failed',
        safeguard_result: 'Verification failed, triggered rollback',
      },
    ];
  }
};

export const startExperiment = async (config: ExperimentConfig) => {
  const exp_id = `exp_${config.policy}_${config.scenario}_ui`;
  const res = await fetch(`${API_BASE}/experiments/${exp_id}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
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
