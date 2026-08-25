import React, { useState } from 'react';
import NetworkMap from './components/NetworkMap';
import InsightsPanel from './components/InsightsPanel';

function App() {
  const [selectedElement, setSelectedElement] = useState<any>(null);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      {/* Header */}
      <header className="glass-panel border-b border-slate-700 px-6 py-4 flex items-center justify-between z-10 sticky top-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center border border-emerald-500/50">
            <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white">Resili<span className="text-emerald-400">Net</span></h1>
        </div>
        <div className="flex gap-4 text-sm font-medium">
          <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> System Active</span>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left: Network Canvas */}
        <section className="flex-1 relative">
          <div className="absolute inset-0 p-4">
            <div className="w-full h-full glass-panel overflow-hidden">
              <NetworkMap onSelectElement={setSelectedElement} />
            </div>
          </div>
        </section>

        {/* Right: Insights Panel */}
        <aside className="w-96 p-4 pl-0">
          <InsightsPanel selectedElement={selectedElement} />
        </aside>
      </main>
    </div>
  );
}

export default App;
