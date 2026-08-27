import React from 'react';

interface DocsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const DocsModal: React.FC<DocsModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="glass-panel w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-fade-in shadow-[0_0_50px_rgba(16,185,129,0.1)]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-700/50 bg-slate-800/80">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center">
              <svg
                className="w-5 h-5 text-emerald-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                ></path>
              </svg>
            </div>
            <h2 className="text-xl font-bold text-white tracking-wide">
              Project Documentation & Metrics
            </h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M6 18L18 6M6 6l12 12"
              ></path>
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-8 bg-slate-900/50 text-slate-300">
          <section>
            <h3 className="text-lg font-semibold text-emerald-400 mb-3 border-b border-slate-700/50 pb-2">
              1. Model Evaluation Metrics (LightGBM)
            </h3>
            <div className="glass-card p-6 text-center">
              <div className="text-amber-400 font-medium border border-amber-500/30 bg-amber-500/10 px-4 py-2 rounded-md inline-block">
                Pending Mininet-based experimental evaluation
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-lg font-semibold text-emerald-400 mb-3 border-b border-slate-700/50 pb-2">
              2. Datasets & Topologies
            </h3>
            <ul className="space-y-2 list-disc list-inside">
              <li>
                <strong className="text-white">Topology Data:</strong> Sourced from the{' '}
                <span className="text-indigo-400">SNDlib (Survivable Network Design Library)</span>{' '}
                dataset to simulate realistic, real-world backbone network structures.
              </li>
              <li>
                <strong className="text-white">Traffic Generation:</strong> Priority-based traffic
                generation using <span className="text-indigo-400">Mininet</span> and{' '}
                <span className="text-indigo-400">iperf</span> (Telemedicine/Critical vs Background
                traffic).
              </li>
              <li>
                <strong className="text-white">Telemetry Extraction:</strong> Custom Python
                collectors hooking into <span className="text-indigo-400">Open vSwitch (OVS)</span>{' '}
                to extract port statistics every 1 second.
              </li>
            </ul>
          </section>

          <section>
            <h3 className="text-lg font-semibold text-emerald-400 mb-3 border-b border-slate-700/50 pb-2">
              3. Data Pipeline & Implementation
            </h3>
            <div className="space-y-4">
              <div>
                <h4 className="text-white font-medium mb-1">Windowing & Feature Engineering</h4>
                <p className="text-sm leading-relaxed">
                  Raw telemetry is observed approximately every two seconds. We generate time-series
                  features over 30-second rolling windows, capturing means, maximums, and
                  rate-of-change estimates (e.g.{' '}
                  <code className="bg-slate-800 px-1.5 py-0.5 rounded text-emerald-300">
                    tx_bytes_rate
                  </code>
                  ,{' '}
                  <code className="bg-slate-800 px-1.5 py-0.5 rounded text-emerald-300">
                    loss_mean_30s
                  </code>
                  ,{' '}
                  <code className="bg-slate-800 px-1.5 py-0.5 rounded text-emerald-300">
                    tx_dropped_max
                  </code>
                  ) to dynamically reflect traffic velocity.
                </p>
              </div>
              <div>
                <h4 className="text-white font-medium mb-1">
                  Machine Learning & Explainable AI (XAI)
                </h4>
                <p className="text-sm leading-relaxed">
                  We trained a <strong>LightGBM</strong> binary classifier to predict future SLA
                  violations (congestion probability). We integrated{' '}
                  <strong>SHAP (SHapley Additive exPlanations)</strong> to map exact feature
                  contributions to predictions, rendering the model fully explainable rather than a
                  black box.
                </p>
              </div>
              <div>
                <h4 className="text-white font-medium mb-1">Predictive Routing Engine</h4>
                <p className="text-sm leading-relaxed">
                  Instead of reactive shortest-path routing, we implemented a predictive{' '}
                  <strong>Dijkstra's Algorithm</strong> via NetworkX. Link weights are inflated
                  dynamically based on the AI's predicted congestion probability, routing critical
                  traffic around bottlenecks before they occur.
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default DocsModal;
