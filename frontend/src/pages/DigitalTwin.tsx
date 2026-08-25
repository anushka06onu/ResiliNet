import React, { useState } from 'react';
import NetworkMap from '../components/NetworkMap'; // Reusing the cytoscape component

const DigitalTwin = () => {
  const [selectedElement, setSelectedElement] = useState<any>(null);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: Cytoscape Canvas */}
      <div className="flex-1 relative">
        <div className="absolute top-4 left-4 z-10 pointer-events-none">
          <h2 className="text-xl font-bold text-white shadow-black drop-shadow-md">Live Digital Twin</h2>
          <p className="text-sm text-slate-300 shadow-black drop-shadow-md">Select a node or link to inspect telemetry.</p>
        </div>
        <NetworkMap onSelectElement={setSelectedElement} />
      </div>

      {/* Right: Inspector Panel */}
      <div className="w-80 border-l border-slate-800 bg-slate-900/80 p-4 overflow-y-auto flex flex-col gap-4">
        <h3 className="text-lg font-semibold text-white border-b border-slate-700 pb-2">Inspector</h3>
        
        {!selectedElement ? (
          <p className="text-slate-500 text-sm">No element selected.</p>
        ) : selectedElement.type === 'link' ? (
          <div className="space-y-4">
            <div>
              <span className="text-xs text-slate-400 uppercase tracking-widest">Link</span>
              <div className="text-lg font-bold text-white">{selectedElement.source} → {selectedElement.target}</div>
            </div>
            
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="bg-slate-800 p-2 rounded">
                <span className="text-slate-400 block text-xs">Capacity (Bandwidth)</span>
                <span className="text-white">1 Gbps</span>
              </div>
              <div className="bg-slate-800 p-2 rounded">
                <span className="text-slate-400 block text-xs">How Full? (Utilization)</span>
                <span className="text-amber-400">81%</span>
              </div>
              <div className="bg-slate-800 p-2 rounded">
                <span className="text-slate-400 block text-xs">Delay (Latency)</span>
                <span className="text-white">63.2 ms</span>
              </div>
              <div className="bg-slate-800 p-2 rounded">
                <span className="text-slate-400 block text-xs">Lost Packets</span>
                <span className="text-emerald-400">0.018%</span>
              </div>
            </div>

            <div className="bg-amber-900/20 border border-amber-500/50 p-3 rounded-lg mt-4">
              <span className="text-xs text-amber-500 font-bold uppercase tracking-widest block mb-1">AI Prediction</span>
              <div className="flex justify-between items-end">
                <span className="text-slate-300 text-sm">Congestion risk score</span>
                <span className="text-2xl font-bold text-amber-500">87/100</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 mt-2 rounded overflow-hidden">
                <div className="bg-amber-500 h-full" style={{ width: '87%' }}></div>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <span className="text-xs text-slate-400 uppercase tracking-widest">Switch</span>
              <div className="text-lg font-bold text-white">{selectedElement.id}</div>
            </div>
            <div className="bg-slate-800 p-3 rounded text-sm">
              <span className="text-slate-400 block mb-1">Active Flows</span>
              <span className="text-white font-mono">14</span>
            </div>
            <div className="bg-slate-800 p-3 rounded text-sm">
              <span className="text-slate-400 block mb-1">Installed Rules</span>
              <span className="text-white font-mono">234</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DigitalTwin;
