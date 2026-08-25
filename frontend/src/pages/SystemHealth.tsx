
import { Activity, Server, Cpu, Database, Network, Clock, CheckCircle, XCircle } from 'lucide-react';
import { useStore } from '../store/useStore';

const SystemHealth = () => {
  const { systemStatus } = useStore();

  const metrics = [
    { label: 'Collector Status', value: 'Not connected', icon: <Database size={16} />, status: 'error' },
    { label: 'Model Version', value: 'Development artifact', icon: <Cpu size={16} />, status: 'info' },
    { label: 'WebSocket Connection', value: systemStatus === 'connected' ? 'Connected' : 'Disconnected', icon: <Network size={16} />, status: systemStatus === 'connected' ? 'good' : 'error' },
    { label: 'Controller Status', value: 'Not connected', icon: <Server size={16} />, status: 'error' },
    { label: 'Experiment Source', value: 'Synthetic', icon: <Clock size={16} />, status: 'info' },
  ];

  const recentLogs = [
    { time: '14:32:15', level: 'INFO', message: 'WebSocket connection established successfully.' },
    { time: '14:32:16', level: 'INFO', message: 'Loaded topology: sndlib_campus.xml' },
    { time: '14:32:18', level: 'INFO', message: 'Model loaded: resili_lgbm_v1.4.2.pkl' },
    { time: '14:35:10', level: 'WARN', message: 'Link s2-s4 latency deviation detected (Z-score > 2.0)' },
    { time: '14:35:12', level: 'SUCCESS', message: 'Route calculation completed in 4ms.' },
    { time: '14:35:13', level: 'SUCCESS', message: 'ovs-ofctl applied 3 flow rules successfully.' },
  ];

  return (
    <div className="p-6 h-full overflow-y-auto">
      <header className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
          <Activity className="text-emerald-500" />
          System Health and Audit Log
        </h2>
        <p className="text-slate-400 text-sm">
          Displays collector status, model version, connection health, and system errors for technical auditing.
        </p>
      </header>

      <div className="grid grid-cols-3 gap-6 mb-8">
        {metrics.map((metric, i) => (
          <div key={i} className="bg-slate-900 border border-slate-800 p-4 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-full ${metric.status === 'good' ? 'bg-emerald-500/20 text-emerald-400' : metric.status === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-indigo-500/20 text-indigo-400'}`}>
                {metric.icon}
              </div>
              <div>
                <p className="text-xs text-slate-500">{metric.label}</p>
                <p className="text-white font-medium">{metric.value}</p>
              </div>
            </div>
            {metric.status === 'good' && <CheckCircle size={16} className="text-emerald-500/50" />}
            {metric.status === 'error' && <XCircle size={16} className="text-red-500/50" />}
          </div>
        ))}
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/50">
          <h3 className="font-bold text-slate-200">System Audit Log</h3>
        </div>
        <div className="p-0">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-800/50 text-slate-400">
              <tr>
                <th className="px-6 py-3 font-medium">Timestamp</th>
                <th className="px-6 py-3 font-medium">Level</th>
                <th className="px-6 py-3 font-medium">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {recentLogs.map((log, i) => (
                <tr key={i} className="hover:bg-slate-800/20 transition-colors text-slate-300">
                  <td className="px-6 py-4 font-mono text-xs text-slate-500">{log.time}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs font-bold rounded ${
                      log.level === 'INFO' ? 'bg-indigo-500/10 text-indigo-400' :
                      log.level === 'WARN' ? 'bg-amber-500/10 text-amber-400' :
                      log.level === 'SUCCESS' ? 'bg-emerald-500/10 text-emerald-400' :
                      'bg-red-500/10 text-red-400'
                    }`}>
                      {log.level}
                    </span>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs">{log.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default SystemHealth;
