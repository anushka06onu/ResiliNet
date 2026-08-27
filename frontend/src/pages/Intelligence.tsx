import { BrainCircuit, Info } from 'lucide-react';

const Intelligence = () => {
  return (
    <div className="p-6 h-full overflow-y-auto">
      <header className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
          <BrainCircuit className="text-indigo-500" />
          Predictive Intelligence
        </h2>
        <div className="flex items-center gap-4">
          <p className="text-slate-400 text-sm">
            Real-time inference and model explanations from the predictive engine.
          </p>
          <div className="bg-amber-900/30 text-amber-400 border border-amber-500/50 px-3 py-1.5 rounded-md text-xs font-bold tracking-wider uppercase">
            DEMO SCENARIO — VALUES ARE ILLUSTRATIVE
          </div>
        </div>
      </header>

      <div className="grid grid-cols-3 gap-6 mb-8">
        {/* Metric Cards */}
        <div className="col-span-2 bg-slate-900 border border-slate-800 p-6 rounded-lg flex items-center justify-center">
          <div className="text-center">
            <p className="text-slate-400 text-sm font-medium uppercase tracking-widest mb-3">
              Model Evaluation Metrics
            </p>
            <div className="text-amber-400 border border-amber-500/30 bg-amber-500/10 px-4 py-2 rounded-md font-medium inline-block">
              Pending Mininet-based experimental evaluation
            </div>
          </div>
        </div>

        {/* Info Panel */}
        <div className="bg-indigo-900/10 border border-indigo-500/20 p-5 rounded-lg flex flex-col justify-center">
          <div className="flex items-start gap-3">
            <Info className="text-indigo-400 shrink-0 mt-1" size={20} />
            <div>
              <h4 className="text-indigo-300 font-bold mb-2">Model Architecture</h4>
              <p className="text-slate-300">
                Telemetry is observed approximately every two seconds, with rolling statistics
                calculated over the previous 30 seconds.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 h-80">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col">
          <h3 className="text-slate-300 font-medium mb-1">AI Precision-Recall Curve</h3>
          <p className="text-xs text-slate-500 mb-3">
            Shows how well the AI balances catching real problems vs raising false alarms.
          </p>
          <div className="flex-1 flex items-center justify-center border border-dashed border-slate-700/50 rounded bg-slate-800/20 text-slate-500">
            [PR Curve Graph Component]
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col">
          <h3 className="text-slate-300 font-medium mb-1">SHAP Feature Explanations</h3>
          <div className="flex-1 overflow-y-auto space-y-3">
            <p className="text-xs text-slate-400 mb-2">
              TreeSHAP estimates each feature’s contribution to an individual LightGBM output
              relative to the model’s expected output. The dashboard presents the observed feature
              value, contribution direction and a plain-language interpretation. The displayed
              explanation is treated as a model explanation, not as proof of a causal relationship.
            </p>

            <div className="bg-slate-800/50 p-3 rounded">
              <div className="mb-2">
                <span className="text-sm text-slate-300 font-mono font-bold">
                  Feature: Transmission-rate slope
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs mb-2 border-l-2 border-amber-500 pl-2">
                <div>
                  <span className="text-slate-500">Observed value:</span>{' '}
                  <span className="text-slate-300">+4.8 Mbps/s</span>
                </div>
                <div>
                  <span className="text-slate-500">SHAP contribution:</span>{' '}
                  <span className="text-amber-400">+0.31 model units</span>
                </div>
              </div>
              <div className="text-xs text-slate-400 italic">
                Human explanation: Rapid traffic growth increased predicted risk.
              </div>
            </div>

            <div className="bg-slate-800/50 p-3 rounded">
              <div className="mb-2">
                <span className="text-sm text-slate-300 font-mono font-bold">
                  Feature: Packet loss mean (30s)
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs mb-2 border-l-2 border-amber-500 pl-2">
                <div>
                  <span className="text-slate-500">Observed value:</span>{' '}
                  <span className="text-slate-300">0.012</span>
                </div>
                <div>
                  <span className="text-slate-500">SHAP contribution:</span>{' '}
                  <span className="text-amber-400">+0.15 model units</span>
                </div>
              </div>
              <div className="text-xs text-slate-400 italic">
                Human explanation: Sustained minor packet loss contributed moderately to risk.
              </div>
            </div>

            <div className="bg-slate-800/50 p-3 rounded">
              <div className="mb-2">
                <span className="text-sm text-slate-300 font-mono font-bold">
                  Feature: Dropped packets (max)
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs mb-2 border-l-2 border-emerald-500 pl-2">
                <div>
                  <span className="text-slate-500">Observed value:</span>{' '}
                  <span className="text-slate-300">0</span>
                </div>
                <div>
                  <span className="text-slate-500">SHAP contribution:</span>{' '}
                  <span className="text-emerald-400">-0.22 model units</span>
                </div>
              </div>
              <div className="text-xs text-slate-400 italic">
                Human explanation: Zero dropped packets decreased the predicted risk.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Intelligence;
