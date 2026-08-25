import React, { useState, useEffect } from 'react';
import NetworkMap from './components/NetworkMap';
import InsightsPanel from './components/InsightsPanel';
import { isSimulationMode } from './services/api';

function App() {
  const [selectedElement, setSelectedElement] = useState<any>(null);
  const [time, setTime] = useState(new Date().toLocaleTimeString());
  const [simMode, setSimMode] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date().toLocaleTimeString());
      setSimMode(isSimulationMode);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen text-slate-100 flex flex-col font-sans overflow-hidden">
      {/* Header */}
      <header className="glass-panel border-b border-slate-800 px-6 py-4 flex items-center justify-between z-10 m-4 mb-2">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white m-0 leading-tight">Resili<span className="text-emerald-400 glow-text-green">Net</span></h1>
            <p className="text-xs text-slate-400 tracking-widest uppercase font-mono">Digital Twin NOC</p>
          </div>
        </div>
        
        <div className="flex gap-6 items-center">
          <div className="font-mono text-slate-300 bg-slate-900/50 px-4 py-1.5 rounded-lg border border-slate-700/50">
            {time}
          </div>
          {simMode ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-sm font-medium">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span> Simulation Mode
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-sm font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]"></span> Live Telemetry Active
            </div>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden p-4 pt-2 gap-4">
        {/* Left: Network Canvas */}
        <section className="flex-1 relative glass-panel overflow-hidden group">
          <div className="absolute top-4 left-4 z-10 pointer-events-none opacity-50 group-hover:opacity-100 transition-opacity">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"></path></svg>
              Network Topology Map
            </h2>
          </div>
          <NetworkMap onSelectElement={setSelectedElement} />
        </section>

        {/* Right: Insights Panel */}
        <aside className="w-96 flex flex-col gap-4">
          <InsightsPanel selectedElement={selectedElement} />
        </aside>
      </main>
    </div>
  );
}

export default App;
