
import { Activity, ShieldCheck, AlertTriangle, Route } from 'lucide-react';
import { useStore } from '../store/useStore';

const NetworkOverview = () => {
  const { activeConnections, currentTopology, linkStates, latestTelemetry } = useStore();
  
  // Calculate dynamic stats
  const totalLinks = currentTopology?.links?.length || 0;
  const atRiskLinks = Object.values(linkStates).filter(s => (s.predicted_risk || 0) > 0.8).length;
  // We consider all non-at-risk links healthy for now in demo
  const healthyLinks = totalLinks - atRiskLinks;



  return (
    <div className="p-6 h-full overflow-y-auto">
      <header className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">Network Overview</h2>
        <div className="flex gap-4 text-sm items-center">
          <span className="px-2 py-1 bg-slate-800 rounded text-slate-300">Topology: <strong className="text-white">sndlib_campus_demo</strong></span>
          <span className="px-2 py-1 bg-slate-800 rounded text-slate-300">Experiment: <strong className="text-white">{latestTelemetry?.experiment_id || "None"}</strong></span>
          <span className="px-2 py-1 bg-slate-800 rounded text-slate-300">Connections: <strong className="text-emerald-400">{activeConnections}</strong></span>
          <div className="bg-amber-900/30 text-amber-400 border border-amber-500/50 px-3 py-1 rounded-md text-xs font-bold tracking-wider uppercase ml-auto">
            ILLUSTRATIVE DEMO SCENARIO
          </div>
        </div>
      </header>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm font-medium">Network Health</p>
            <div className="text-2xl font-bold text-white mt-1">
              <span className="text-emerald-400">{healthyLinks}</span> / {totalLinks}
            </div>
            <p className="text-xs text-slate-500 mt-1">Healthy Links</p>
          </div>
          <Activity className="text-emerald-500/50" size={32} />
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm font-medium">Critical Flows</p>
            <div className="text-2xl font-bold text-white mt-1">Pending</div>
            <p className="text-xs text-emerald-500 mt-1 flex items-center gap-1"><ShieldCheck size={12}/> Monitoring</p>
          </div>
          <ShieldCheck className="text-indigo-500/50" size={32} />
        </div>

        <div className="bg-slate-900 border border-amber-900/50 p-4 rounded-lg flex items-center justify-between">
          <div>
            <p className="text-amber-500 text-sm font-medium">At-Risk Links</p>
            <div className="text-2xl font-bold text-white mt-1">{atRiskLinks}</div>
            <p className="text-xs text-amber-500/70 mt-1">Predicted risk {'>'} 80%</p>
          </div>
          <AlertTriangle className="text-amber-500/50" size={32} />
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm font-medium">Predictive Reroutes</p>
            <div className="text-2xl font-bold text-white mt-1">Pending</div>
            <p className="text-xs text-indigo-400 mt-1">Experimental validation pending</p>
          </div>
          <Route className="text-purple-500/50" size={32} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 h-96">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col">
          <h3 className="text-slate-300 font-medium mb-4">Overall Network Risk Timeline</h3>
          <div className="flex-1 flex items-center justify-center border border-dashed border-slate-700/50 rounded bg-slate-800/20 text-slate-500">
            [Risk Timeline Chart]
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col">
          <h3 className="text-slate-300 font-medium mb-4">Alert Lifecycle (Flow 1: Telemedicine)</h3>
          <div className="flex-1 overflow-y-auto space-y-2 relative pl-4 border-l-2 border-slate-700 ml-2">
            
            <div className="relative">
              <div className="absolute -left-[21px] top-1 w-3 h-3 rounded-full bg-amber-500 border-2 border-slate-900"></div>
              <p className="text-xs font-bold text-amber-500">14:31:58 - Detected & Explained</p>
              <p className="text-sm text-slate-300">Link s2-s4 congestion risk reached 85/100. Strongest contributor: Rapid traffic growth.</p>
            </div>

            <div className="relative mt-4">
              <div className="absolute -left-[21px] top-1 w-3 h-3 rounded-full bg-indigo-500 border-2 border-slate-900"></div>
              <p className="text-xs font-bold text-indigo-400">14:31:59 - Route Proposed & Safety Checked</p>
              <p className="text-sm text-slate-300">Alternative path S1-S3-S7 calculated via Dijkstra. Safety checks passed (No loops detected).</p>
            </div>

            <div className="relative mt-4">
              <div className="absolute -left-[21px] top-1 w-3 h-3 rounded-full bg-purple-500 border-2 border-slate-900"></div>
              <p className="text-xs font-bold text-purple-400">14:32:00 - Rule Installed</p>
              <p className="text-sm text-slate-300">OpenFlow rules injected via `ovs-ofctl`. Original route retained as backup.</p>
            </div>

            <div className="relative mt-4">
              <div className="absolute -left-[21px] top-1 w-3 h-3 rounded-full bg-emerald-500 border-2 border-slate-900"></div>
              <p className="text-xs font-bold text-emerald-400">14:32:01 - Route Verification (Demo)</p>
              <p className="text-sm text-slate-300">In a live lab, port counters will verify if traffic shifted and latency improved.</p>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
};

export default NetworkOverview;
