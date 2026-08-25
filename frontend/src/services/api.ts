const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

// Global state to track if we are in live mode or simulation mode
export let isSimulationMode = false;

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
    { id: 'server1', type: 'host' }
  ],
  links: [
    { source: 'core1', target: 'core2' },
    { source: 'core1', target: 'dist1' },
    { source: 'core2', target: 'dist2' },
    { source: 'dist1', target: 'acc1' },
    { source: 'dist2', target: 'acc2' },
    { source: 'acc1', target: 'h1' },
    { source: 'acc2', target: 'h2' },
    { source: 'core1', target: 'server1' }
  ]
};

export const getTopology = async () => {
  try {
    const res = await fetch(`${API_BASE}/topology/current`);
    if (!res.ok) throw new Error('Network response was not ok');
    isSimulationMode = false;
    return await res.json();
  } catch (error) {
    console.warn("Backend unreachable, falling back to Simulation Mode for Topology.");
    isSimulationMode = true;
    return MOCK_TOPOLOGY;
  }
};

export const getPredictionAndExplanation = async (source: string, target: string) => {
  try {
    if (isSimulationMode) throw new Error('Force mock'); // Skip fetch if we are in DEMO DATA mode
    
    // In live mode, we fetch both predict and explain and combine them to match the frontend contract
    const predictRes = await fetch(`${API_BASE}/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ switch_id: source, port_no: target, features: {} })
    });
    
    const explainRes = await fetch(`${API_BASE}/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ switch_id: source, port_no: target, features: {} })
    });

    if (!predictRes.ok || !explainRes.ok) throw new Error('Network response was not ok');
    
    const predictData = await predictRes.json();
    const explainData = await explainRes.json();

    return {
      predict: predictData,
      explain: explainData
    };
  } catch (error) {
    // Realistic Mock Data for Simulation Mode (DEMO DATA)
    return new Promise((resolve) => {
      setTimeout(() => {
        // Deterministic mock based on link names to simulate a persistent congested link
        const isCongested = (source === 'dist2' && target === 'acc2') || (source === 'core1' && target === 'dist1');
        const prob = isCongested ? 0.88 : (Math.random() * 0.15 + 0.05);
        
        resolve({
          predict: {
            congestion_probability: prob,
            is_violation_predicted: prob > 0.5
          },
          explain: {
            base_value: 0.1,
            features: [
              { name: 'loss_mean_30s', value: isCongested ? 45.2 : 0.1, shap_contribution: isCongested ? 0.45 : -0.1 },
              { name: 'tx_bytes_rate', value: 1048576, shap_contribution: 0.2 },
              { name: 'rx_bytes_slope', value: -500, shap_contribution: -0.05 },
              { name: 'tx_dropped_max', value: isCongested ? 100 : 0, shap_contribution: isCongested ? 0.15 : -0.02 }
            ]
          }
        });
      }, 400); // simulate network latency
    });
  }
};
