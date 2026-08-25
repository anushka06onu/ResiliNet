// Mock API service for local demonstration since backend requires Mininet/OVS

const API_BASE = 'http://localhost:8000/api/v1';
const USE_MOCK = true; // Set to false if backend is running

export const getTopology = async () => {
  if (USE_MOCK) {
    // Return a mocked campus topology matching Phase 3
    return {
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
  }
  const res = await fetch(`${API_BASE}/topology`);
  return res.json();
};

export const getPredictionAndExplanation = async (source: string, target: string) => {
  if (USE_MOCK) {
    return new Promise((resolve) => {
      setTimeout(() => {
        // Randomly simulate congestion on some links
        const isCongested = Math.random() > 0.7;
        const prob = isCongested ? 0.85 : 0.12;
        
        resolve({
          predict: {
            congestion_probability: prob,
            is_violation_predicted: isCongested
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
      }, 600);
    });
  }
  
  // Real implementation would post the actual features
  return { predict: {}, explain: {} };
};
