import React, { useEffect, useState } from 'react';
import { getPredictionAndExplanation } from '../services/api';

interface InsightsPanelProps {
  selectedElement: any;
}

const InsightsPanel: React.FC<InsightsPanelProps> = ({ selectedElement }) => {
  const [insight, setInsight] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (selectedElement && selectedElement.type === 'edge') {
      setLoading(true);
      getPredictionAndExplanation(selectedElement.data.source, selectedElement.data.source_port)
        .then(data => {
          setInsight(data);
          setLoading(false);
        })
        .catch(err => {
          console.error(err);
          setLoading(false);
        });
    } else {
      setInsight(null);
    }
  }, [selectedElement]);

  if (!selectedElement) {
    return (
      <div className="w-full h-full glass-panel flex flex-col items-center justify-center text-slate-400 p-8 text-center">
        <svg className="w-12 h-12 text-slate-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"></path></svg>
        <p className="text-lg font-medium text-slate-300">No Target Selected</p>
        <p className="text-sm mt-2">Click on a network node or link on the map to view real-time telemetry and predictive AI insights.</p>
      </div>
    );
  }

  const isEdge = selectedElement.type === 'edge';
  const prob = insight?.predict?.congestion_probability || 0;
  const isCongested = prob > 0.5;

  return (
    <div className="w-full h-full glass-panel flex flex-col overflow-hidden">
      <div className="p-5 border-b border-slate-700/50 bg-slate-800/40">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-600 flex items-center justify-center">
            {isEdge ? (
              <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
            ) : (
              <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
            )}
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white tracking-wide">Inspector</h2>
            <p className="text-xs text-slate-400 font-mono">ID: {selectedElement.id}</p>
          </div>
        </div>
      </div>

      <div className="p-5 flex-1 overflow-y-auto">
        {!isEdge ? (
          <div className="space-y-4">
            <h3 className="text-xs uppercase tracking-widest text-slate-500 font-bold">Node Properties</h3>
            <div className="glass-card p-4 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-slate-400 text-sm">Role</span>
                <span className="text-slate-200 capitalize font-medium bg-slate-700/50 px-2 py-0.5 rounded">{selectedElement.data.type || 'Host'}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400 text-sm">Status</span>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 glow-border-green"></span>
                  <span className="text-emerald-400 text-sm font-medium glow-text-green">Online</span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <h3 className="text-xs uppercase tracking-widest text-slate-500 font-bold mb-3">Predictive SLA Risk</h3>
              
              <div className={`glass-card p-4 relative overflow-hidden ${isCongested && !loading ? 'glow-border-red border-red-500/50 bg-red-950/20' : 'border-slate-700/40'}`}>
                {/* Background pulse for high risk */}
                {isCongested && !loading && <div className="absolute inset-0 bg-red-500/5 animate-pulse"></div>}
                
                <div className="relative flex justify-between items-center">
                  <span className="text-slate-300 font-medium">Congestion Probability</span>
                  {loading ? (
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-emerald-500/50 border-t-emerald-500 rounded-full animate-spin"></div>
                      <span className="text-slate-500 text-sm font-mono">CALC...</span>
                    </div>
                  ) : (
                    <span className={`text-2xl font-bold font-mono tracking-tight ${isCongested ? 'text-red-400 glow-text-red' : 'text-emerald-400 glow-text-green'}`}>
                      {(prob * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
                
                {!loading && (
                  <div className="mt-3 h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full transition-all duration-1000 ${isCongested ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]' : 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]'}`}
                      style={{ width: `${prob * 100}%` }}
                    ></div>
                  </div>
                )}
              </div>
            </div>

            <div>
              <h3 className="text-xs uppercase tracking-widest text-slate-500 font-bold mb-3">XAI SHAP Analysis</h3>
              
              <div className="glass-card p-4">
                {loading ? (
                  <div className="space-y-4">
                    {[1,2,3,4].map(i => (
                      <div key={i} className="flex flex-col gap-2">
                        <div className="flex justify-between"><div className="h-3 bg-slate-700/50 rounded w-24 animate-pulse"></div><div className="h-3 bg-slate-700/50 rounded w-8 animate-pulse"></div></div>
                        <div className="h-1.5 bg-slate-800 rounded w-full"><div className="h-full bg-slate-700/50 rounded w-1/2 animate-pulse"></div></div>
                      </div>
                    ))}
                  </div>
                ) : insight?.explain ? (
                  <div className="space-y-4">
                    <p className="text-xs text-slate-400 mb-4 leading-relaxed">Features driving the risk prediction. Positive values increase congestion risk.</p>
                    {insight.explain.features.map((f: any, idx: number) => {
                      const isPositive = f.shap_contribution > 0;
                      // Normalize width for display (max SHAP usually < 2 in this model, scale arbitrarily for visual impact)
                      const maxAbsShap = Math.max(...insight.explain.features.map((fx:any) => Math.abs(fx.shap_contribution)), 0.1);
                      const width = Math.min(100, Math.max(5, (Math.abs(f.shap_contribution) / maxAbsShap) * 100));
                      
                      return (
                        <div key={idx} className="relative group">
                          <div className="flex justify-between text-xs mb-1.5">
                            <span className="text-slate-300 font-mono truncate w-32" title={f.name}>{f.name}</span>
                            <span className={`font-mono font-medium ${isPositive ? 'text-red-400' : 'text-emerald-400'}`}>
                              {isPositive ? '+' : ''}{f.shap_contribution.toFixed(3)}
                            </span>
                          </div>
                          {/* Centered divergent bar chart */}
                          <div className="w-full bg-slate-900 rounded-full h-2 flex items-center">
                            <div className="flex-1 flex justify-end h-full">
                              {!isPositive && <div className="bg-gradient-to-l from-emerald-400 to-emerald-600 h-full rounded-l-full shadow-[0_0_8px_rgba(16,185,129,0.5)] transition-all duration-1000" style={{ width: `${width}%` }}></div>}
                            </div>
                            <div className="w-px h-3 bg-slate-600 z-10"></div>
                            <div className="flex-1 h-full">
                              {isPositive && <div className="bg-gradient-to-r from-red-400 to-red-600 h-full rounded-r-full shadow-[0_0_8px_rgba(239,68,68,0.5)] transition-all duration-1000" style={{ width: `${width}%` }}></div>}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-slate-500 text-sm italic text-center py-4">Explanation data unavailable.</div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default InsightsPanel;
