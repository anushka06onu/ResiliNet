import { Search, Filter } from 'lucide-react';

const mockFlows = [
  { id: 'f_001', src: 'h1', dst: 'server1', category: 'Telemedicine', tier: 'Critical', path: 's1 → s3 → s7', latency: '12.4ms', loss: '0.0%', tput: '45 Mbps', sla: 'Healthy', risk: '12%' },
  { id: 'f_002', src: 'h2', dst: 'server2', category: 'Education', tier: 'Video', path: 's2 → s4 → s8', latency: '34.1ms', loss: '0.1%', tput: '12 Mbps', sla: 'At-Risk', risk: '65%' },
  { id: 'f_003', src: 'h3', dst: 'server1', category: 'Background', tier: 'Bulk', path: 's5 → s6 → s7', latency: '120.5ms', loss: '2.4%', tput: '85 Mbps', sla: 'Violated', risk: '98%' },
];

const FlowMonitor = () => {
  return (
    <div className="p-6 h-full flex flex-col">
      <header className="mb-6 flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Flow & SLA Monitor</h2>
          <p className="text-slate-400 text-sm">Real-time Quality of Service tracking for active application flows.</p>
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
            <input type="text" placeholder="Search flows..." className="bg-slate-900 border border-slate-700 text-sm rounded pl-9 pr-3 py-1.5 focus:outline-none focus:border-emerald-500 text-white" />
          </div>
          <button className="bg-slate-800 border border-slate-700 px-3 py-1.5 rounded flex items-center gap-2 text-sm text-slate-300 hover:text-white">
            <Filter size={16} /> Filter
          </button>
        </div>
      </header>

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden flex-1 flex flex-col">
        <table className="w-full text-left text-sm text-slate-300">
          <thead className="bg-slate-800/50 text-xs uppercase text-slate-500 font-semibold border-b border-slate-800">
            <tr>
              <th className="px-4 py-3">Flow ID</th>
              <th className="px-4 py-3">Src → Dst</th>
              <th className="px-4 py-3">App Category</th>
              <th className="px-4 py-3">Current Path</th>
              <th className="px-4 py-3">Latency</th>
              <th className="px-4 py-3">Loss</th>
              <th className="px-4 py-3">SLA Status</th>
              <th className="px-4 py-3">Predicted Risk</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {mockFlows.map((flow) => (
              <tr key={flow.id} className="hover:bg-slate-800/30 transition-colors cursor-pointer group">
                <td className="px-4 py-3 font-mono text-emerald-400">{flow.id}</td>
                <td className="px-4 py-3 font-medium text-white">{flow.src} &rarr; {flow.dst}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-col">
                    <span className="text-slate-200">{flow.category}</span>
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">{flow.tier}</span>
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs">{flow.path}</td>
                <td className="px-4 py-3">{flow.latency}</td>
                <td className="px-4 py-3">{flow.loss}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-bold uppercase tracking-wider
                    ${flow.sla === 'Healthy' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 
                      flow.sla === 'At-Risk' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                      'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                    {flow.sla}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className={`w-8 ${parseInt(flow.risk) > 50 ? 'text-amber-400' : 'text-slate-400'}`}>{flow.risk}</span>
                    <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden">
                      <div className={`h-full ${parseInt(flow.risk) > 80 ? 'bg-red-500' : parseInt(flow.risk) > 50 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{width: flow.risk}}></div>
                    </div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        
        {/* Detail drawer (hidden initially) */}
        <div className="mt-auto border-t border-slate-800 bg-slate-900/50 p-4 text-center text-slate-500 text-sm">
          Select a flow to highlight its path on the topology map.
        </div>
      </div>
    </div>
  );
};

export default FlowMonitor;
