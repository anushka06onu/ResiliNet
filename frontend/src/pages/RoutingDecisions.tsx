import { useState, useEffect } from 'react';
import { Route, CheckCircle, XCircle } from 'lucide-react';
import { getRoutingDecisions } from '../services/api';
import type { RoutingResult } from '../services/api';

const RoutingDecisions = () => {
  const [decisions, setDecisions] = useState<RoutingResult[]>([]);

  useEffect(() => {
    const fetchDecisions = async () => {
      try {
        const data = await getRoutingDecisions();
        const sorted = data.sort(
          (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
        );
        setDecisions(sorted);
      } catch (err) {
        console.error('Failed to fetch routing decisions', err);
      }
    };
    fetchDecisions();
    const interval = setInterval(fetchDecisions, 3000);
    return () => clearInterval(interval);
  }, []);

  const latest = decisions[0];

  return (
    <div className="p-6 h-full flex flex-col">
      <header className="mb-6 flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
            <Route className="text-purple-500" />
            Routing Decisions Log
          </h2>
          <p className="text-slate-400 text-sm">
            Audit log of automated traffic engineering and path modifications.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-3 gap-6 flex-1">
        {/* Comparison Table */}
        <div className="col-span-2 flex flex-col h-full bg-slate-900 border border-slate-800 rounded-lg p-4">
          <h3 className="text-slate-300 font-medium mb-4">
            Before vs After Rerouting {latest ? `(Flow ${latest.flow_id})` : ''}
          </h3>
          <table className="w-full text-left text-sm text-slate-300 mb-6">
            <thead className="bg-slate-800/50 text-xs uppercase text-slate-500 font-semibold border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Measurement</th>
                <th className="px-4 py-3">Before Rerouting</th>
                <th className="px-4 py-3 text-purple-400">After Rerouting</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              <tr>
                <td className="px-4 py-3 font-medium">Risk Score</td>
                <td className="px-4 py-3 text-red-400 font-bold">
                  {latest?.risk_before ? (latest.risk_before * 100).toFixed(0) + '/100' : 'Pending'}
                </td>
                <td className="px-4 py-3 text-emerald-400 font-bold">
                  {latest?.risk_after ? (latest.risk_after * 100).toFixed(0) + '/100' : 'Pending'}
                </td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-medium">Latency</td>
                <td className="px-4 py-3">Pending</td>
                <td className="px-4 py-3 text-emerald-400 font-bold">Pending</td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-medium">Packet Loss</td>
                <td className="px-4 py-3">Pending</td>
                <td className="px-4 py-3 text-emerald-400 font-bold">Pending</td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-medium">Throughput</td>
                <td className="px-4 py-3">Pending</td>
                <td className="px-4 py-3 text-emerald-400 font-bold">Pending</td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-medium">Path</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {latest?.original_path ? latest.original_path.join(' → ') : 'Pending'}
                </td>
                <td className="px-4 py-3 font-mono text-xs">
                  {latest?.proposed_path ? latest.proposed_path.join(' → ') : 'Pending'}
                </td>
              </tr>
            </tbody>
          </table>

          <h3 className="text-slate-300 font-medium mb-4">Recent Predictive Interventions</h3>
          <div className="flex-1 overflow-y-auto space-y-3">
            {decisions.map((dec, i) => (
              <div key={i} className="bg-slate-800/30 border border-slate-700/50 p-4 rounded-lg">
                <div className="flex justify-between items-start mb-2">
                  <span
                    className={`${dec.installation_status === 'success' ? 'text-emerald-400' : 'text-red-400'} flex items-center gap-1 text-sm font-bold`}
                  >
                    {dec.installation_status === 'success' ? (
                      <CheckCircle size={14} />
                    ) : (
                      <XCircle size={14} />
                    )}
                    {dec.installation_status === 'success' ? 'APPLIED' : 'REJECTED (Safety Check)'}
                  </span>
                  <span className="text-xs text-slate-500">
                    {new Date(dec.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-slate-500 block mb-1">Flow</span>
                    <span className="text-white font-mono">{dec.flow_id}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-1">Trigger</span>
                    <span className="text-white font-mono">{dec.safeguard_result || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-1">Original Path</span>
                    <span className="text-red-400 font-mono">{dec.original_path?.join(' → ')}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-1">New Path</span>
                    <span className="text-emerald-400 font-mono">
                      {dec.proposed_path ? dec.proposed_path.join(' → ') : 'None'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Info Panel */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg flex flex-col">
          <h3 className="text-slate-300 font-medium mb-4">Controller Logic</h3>
          <div className="text-sm text-slate-400 space-y-4">
            <p>
              When the LightGBM engine predicts a high congestion risk for a link, the predictive
              routing controller inflates the NetworkX edge weight for that link dynamically.
            </p>
            <p>It then recalculates the shortest path using Dijkstra's algorithm.</p>
            <div className="bg-slate-800 p-3 rounded border-l-2 border-amber-500">
              <strong className="text-slate-200 block mb-1">Safety Checks</strong>
              <ul className="list-disc list-inside space-y-1">
                <li>Minimum Risk Improvement &ge; 0.2</li>
                <li>Flow Cooldown &ge; 10s</li>
              </ul>
            </div>
            <p>
              If all safety checks pass, the controller is designed to execute `ovs-ofctl add-flow`
              to install high-priority OpenFlow rules in the emulated Open vSwitch network. (This
              page represents an illustrative routing-decision workflow until live controller
              integration is complete).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RoutingDecisions;
