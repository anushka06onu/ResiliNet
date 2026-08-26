
import { FileText, Code } from 'lucide-react';

const Methodology = () => {


  return (
    <div className="p-6 h-full overflow-y-auto">
      <header className="mb-8 flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
            <FileText className="text-emerald-500" />
            Evidence & Methodology
          </h2>
          <p className="text-slate-400 text-sm">Reproducibility and Data Provenance</p>
        </div>
        <div className="flex gap-4">
          <a href="https://github.com/anushka06onu/ResiliNet" target="_blank" rel="noreferrer" className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-colors text-sm">
            <Code size={16} /> View on GitHub
          </a>
        </div>
      </header>

      <div className="max-w-4xl space-y-6">
        <section className="bg-slate-900 border border-slate-800 rounded-lg p-6">
          <h3 className="text-xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Dataset Provenance (Where the data comes from)</h3>
          <ul className="space-y-3 text-sm text-slate-300 list-disc list-inside">
            <li><strong>Topology Sourcing:</strong> Network maps derived from the <em>SNDlib (Survivable Network Design Library)</em> to simulate realistic telecommunication backbones.</li>
            <li><strong>Number of Experiments:</strong> This demonstration currently uses a synthetic telemetry dataset containing 100 generated experiment identifiers. Mininet-based experimental validation is in progress.</li>
            <li><strong>Data Splitting (Preventing AI "Cheating"):</strong> The dataset is split strictly by complete experiments (60% Train, 20% Val, 20% Test) to reduce temporal and scenario leakage between partitions.</li>
          </ul>
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-lg p-6">
          <h3 className="text-xl font-bold text-white mb-4 border-b border-slate-800 pb-2">SLA Threshold Definitions (What counts as a "Failure"?)</h3>
          <p className="text-sm text-slate-400 mb-4">
            The AI considers a link congested if any of the following happens in the next 30 seconds:
          </p>
          <div className="bg-slate-800 p-4 rounded font-mono text-sm text-slate-300">
            y_et = 1 IF:<br/>
            &nbsp;&nbsp;max(U_e) &ge; 0.85 (Utilization &gt; 85%)<br/>
            &nbsp;&nbsp;OR loss_e &ge; 0.02 (Packet Loss &gt; 2%)<br/>
            &nbsp;&nbsp;OR delay_e &ge; 40ms (Application Latency &gt; 40ms)
          </div>
          <p className="text-xs text-slate-500 mt-2 italic">
            Note: Application latency is actively measured using ping tools, giving a true reflection of user experience rather than just router statistics.
          </p>
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-lg p-6">
          <h3 className="text-xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Models & Hyperparameters (The Brains of the Operation)</h3>
          <p className="text-sm text-slate-400 mb-4">
            We don't just trust the AI blindly. We compare it against standard rules (Static Thresholds) and simpler AI models (Random Forest, Logistic Regression) to prove that the advanced LightGBM engine is actually needed.
          </p>
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-800/50 text-xs uppercase text-slate-500 font-semibold border-b border-slate-800">
              <tr>
                <th className="px-4 py-2">Model</th>
                <th className="px-4 py-2">Hyperparameters</th>
                <th className="px-4 py-2">Purpose</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              <tr>
                <td className="px-4 py-3">LightGBM (Proposed)</td>
                <td className="px-4 py-3 font-mono text-xs">lr=0.05, num_leaves=31, is_unbalance=True</td>
                <td className="px-4 py-3 text-emerald-400 font-medium">Predictive Engine</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Random Forest</td>
                <td className="px-4 py-3 font-mono text-xs">n_estimators=100</td>
                <td className="px-4 py-3 text-slate-500">Tree-based Baseline</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Logistic Regression</td>
                <td className="px-4 py-3 font-mono text-xs">max_iter=1000</td>
                <td className="px-4 py-3 text-slate-500">Simple ML Baseline</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Static Threshold</td>
                <td className="px-4 py-3 font-mono text-xs">latency &gt; 30ms</td>
                <td className="px-4 py-3 text-slate-500">Monitoring Baseline</td>
              </tr>
            </tbody>
          </table>
        </section>

      </div>
    </div>
  );
};

export default Methodology;
