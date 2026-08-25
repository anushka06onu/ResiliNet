import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Activity, Route, Settings, PlayCircle, FileText, Share2, Network, ShieldAlert, Server } from 'lucide-react';
import { useStore } from '../../store/useStore';

const Layout = () => {
  const { systemStatus, version } = useStore();

  const navItems = [
    { name: 'Network Overview', path: '/', icon: <Activity size={18} /> },
    { name: 'Digital Twin', path: '/twin', icon: <Network size={18} /> },
    { name: 'Flow & SLA Monitor', path: '/flows', icon: <ShieldAlert size={18} /> },
    { name: 'Predictive Intelligence', path: '/intelligence', icon: <Share2 size={18} /> },
    { name: 'Routing Decisions', path: '/routing', icon: <Route size={18} /> },
    { name: 'Simulation & Replay', path: '/control', icon: <PlayCircle size={18} /> },
    { name: 'Evidence & Methodology', path: '/methodology', icon: <FileText size={18} /> },
    { name: 'System Health & Audit', path: '/health', icon: <Server size={18} /> },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 flex font-sans">
      {/* Sidebar Navigation */}
      <aside className="w-64 border-r border-slate-800 bg-slate-900/50 flex flex-col">
        <div className="p-4 border-b border-slate-800 flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-emerald-600 flex items-center justify-center">
            <Network size={20} className="text-white" />
          </div>
          <div>
            <h1 className="font-bold text-white tracking-wide leading-tight">ResiliNet</h1>
            <p className="text-[10px] text-slate-400 uppercase tracking-widest">NOC Dashboard v{version}</p>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`
              }
            >
              {item.icon}
              {item.name}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-800">
          <div className={`text-xs px-3 py-1.5 rounded-md border text-center font-bold tracking-wider uppercase
            ${systemStatus === 'LIVE LAB' ? 'bg-emerald-900/30 text-emerald-400 border-emerald-500/50' : 
              systemStatus === 'EXPERIMENT REPLAY' ? 'bg-indigo-900/30 text-indigo-400 border-indigo-500/50' :
              systemStatus === 'DISCONNECTED' ? 'bg-red-900/30 text-red-400 border-red-500/50' :
              'bg-slate-800 text-slate-300 border-slate-700'
            }`}
          >
            {systemStatus}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden flex flex-col relative">
        <div className={`w-full py-1.5 text-center text-xs font-bold tracking-widest uppercase text-white shadow-md
          ${systemStatus === 'LIVE LAB' ? 'bg-emerald-600' : 
            systemStatus === 'EXPERIMENT REPLAY' ? 'bg-indigo-600' :
            systemStatus === 'DEMO DATA' ? 'bg-amber-600' :
            systemStatus === 'DISCONNECTED' ? 'bg-red-600' : 'bg-slate-700'
          }`}
        >
          DATA MODE: {systemStatus}
        </div>
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
