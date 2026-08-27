import sys
import re

filename = "frontend/src/pages/RoutingDecisions.tsx"
with open(filename, "r") as f:
    content = f.read()

# Replace imports and add state
new_imports = "import { useState, useEffect } from 'react';\nimport { Route, CheckCircle, XCircle } from 'lucide-react';\nimport { getRoutingDecisions } from '../services/api';"
content = re.sub(r"import \{ Route, CheckCircle, XCircle \} from 'lucide-react';", new_imports, content)

hooks = """const RoutingDecisions = () => {
  const [decisions, setDecisions] = useState<any[]>([]);
  
  useEffect(() => {
    const fetchDecisions = async () => {
      try {
        const data = await getRoutingDecisions();
        // Sort descending by timestamp
        const sorted = data.sort((a: any, b: any) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        setDecisions(sorted);
      } catch (err) {
        console.error("Failed to fetch routing decisions", err);
      }
    };
    fetchDecisions();
    const interval = setInterval(fetchDecisions, 3000);
    return () => clearInterval(interval);
  }, []);

  const latest = decisions[0];
"""
content = content.replace("const RoutingDecisions = () => {", hooks)

# Remove mock data badge
content = content.replace("""        <div className="bg-amber-900/30 text-amber-400 border border-amber-500/50 px-3 py-1.5 rounded-md text-xs font-bold tracking-wider uppercase">
          DEMO SCENARIO — VALUES ARE ILLUSTRATIVE
        </div>""", "")

# Replace the static Before vs After
before_after = """          <h3 className="text-slate-300 font-medium mb-4">Before vs After Rerouting {latest ? `(Flow ${latest.flow_id})` : ''}</h3>
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
                <td className="px-4 py-3 text-red-400 font-bold">{latest?.risk_before ? (latest.risk_before * 100).toFixed(0) + '/100' : 'Pending'}</td>
                <td className="px-4 py-3 text-emerald-400 font-bold">{latest?.risk_after ? (latest.risk_after * 100).toFixed(0) + '/100' : 'Pending'}</td>
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
                <td className="px-4 py-3 font-mono text-xs">{latest?.original_path ? latest.original_path.join(' → ') : 'Pending'}</td>
                <td className="px-4 py-3 font-mono text-xs">{latest?.proposed_path ? latest.proposed_path.join(' → ') : 'Pending'}</td>
              </tr>
            </tbody>
          </table>"""

content = re.sub(r"          <h3 className=\"text-slate-300 font-medium mb-4\">Before vs After Rerouting.*?</table>", before_after, content, flags=re.DOTALL)

# Replace the static Recent Interventions
interventions = """          <h3 className="text-slate-300 font-medium mb-4">Recent Predictive Interventions</h3>
          <div className="flex-1 overflow-y-auto space-y-3">
            {decisions.map((dec, i) => (
              <div key={i} className="bg-slate-800/30 border border-slate-700/50 p-4 rounded-lg">
                <div className="flex justify-between items-start mb-2">
                  <span className={`${dec.installation_status === 'success' ? 'text-emerald-400' : 'text-red-400'} flex items-center gap-1 text-sm font-bold`}>
                    {dec.installation_status === 'success' ? <CheckCircle size={14}/> : <XCircle size={14}/>} 
                    {dec.installation_status === 'success' ? 'APPLIED' : 'REJECTED (Safety Check)'}
                  </span>
                  <span className="text-xs text-slate-500">{new Date(dec.timestamp).toLocaleTimeString()}</span>
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
                    <span className="text-emerald-400 font-mono">{dec.proposed_path ? dec.proposed_path.join(' → ') : 'None'}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>"""

# Remove static divs
content = re.sub(r"          <h3 className=\"text-slate-300 font-medium mb-4\">Recent Predictive Interventions</h3>.*?</div>\s*</div>", interventions, content, flags=re.DOTALL)


with open(filename, "w") as f:
    f.write(content)
