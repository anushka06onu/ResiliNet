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
      // Simulate fetching ML explanation for the selected link
      getPredictionAndExplanation(selectedElement.data.source, selectedElement.data.target)
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
      <div className="w-full h-full glass-panel flex items-center justify-center text-slate-400 text-sm p-6 text-center">
        Select a network link on the map to view predictive SLA insights and SHAP explanations.
      </div>
    );
  }

  return (
    <div className="w-full h-full glass-panel flex flex-col overflow-hidden">
      <div className="p-4 border-b border-slate-700/50 bg-slate-800/80">
        <h2 className="text-lg font-semibold text-white">Element Inspector</h2>
        <p className="text-xs text-slate-400 font-mono mt-1">ID: {selectedElement.id}</p>
      </div>

      <div className="p-4 flex-1 overflow-y-auto">
        {selectedElement.type === 'node' ? (
          <div>
            <h3 className="text-sm uppercase tracking-wider text-slate-500 font-semibold mb-3">Node Details</h3>
            <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-700/50">
              <div className="flex justify-between py-1">
                <span className="text-slate-400">Type</span>
                <span className="text-slate-200 capitalize">{selectedElement.data.type || 'Host'}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-400">Status</span>
                <span className="text-emerald-400 glow-text-green">Online</span>
              </div>
            </div>
          </div>
        ) : (
          <div>
            <h3 className="text-sm uppercase tracking-wider text-slate-500 font-semibold mb-3">Link Telemetry</h3>
            
            <div className="flex justify-between items-center bg-slate-900/50 rounded-lg p-3 border border-slate-700/50 mb-6">
              <span className="text-slate-400">Congestion Risk</span>
              {loading ? (
                <span className="text-slate-500 animate-pulse">Analyzing...</span>
              ) : (
                <span className={`font-bold ${insight?.predict?.congestion_probability > 0.5 ? 'text-red-400 glow-text-red' : 'text-emerald-400 glow-text-green'}`}>
                  {((insight?.predict?.congestion_probability || 0.05) * 100).toFixed(1)}%
                </span>
              )}
            </div>

            <h3 className="text-sm uppercase tracking-wider text-slate-500 font-semibold mb-3">AI Explainability (SHAP)</h3>
            
            {loading ? (
              <div className="space-y-3">
                <div className="h-4 bg-slate-700/50 rounded w-full animate-pulse"></div>
                <div className="h-4 bg-slate-700/50 rounded w-5/6 animate-pulse"></div>
                <div className="h-4 bg-slate-700/50 rounded w-4/6 animate-pulse"></div>
              </div>
            ) : insight?.explain ? (
              <div className="space-y-4">
                <p className="text-xs text-slate-400 mb-2">Features driving the risk prediction:</p>
                {insight.explain.features.map((f: any, idx: number) => {
                  const isPositive = f.shap_contribution > 0;
                  const width = Math.min(100, Math.max(5, Math.abs(f.shap_contribution) * 100));
                  
                  return (
                    <div key={idx} className="relative">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-300 font-mono truncate w-24" title={f.name}>{f.name}</span>
                        <span className={isPositive ? 'text-red-400' : 'text-emerald-400'}>
                          {isPositive ? '+' : ''}{f.shap_contribution.toFixed(3)}
                        </span>
                      </div>
                      <div className="w-full bg-slate-900 rounded-full h-1.5 flex">
                        {!isPositive && <div className="flex-1 flex justify-end"><div className="bg-emerald-500 h-1.5 rounded-l-full" style={{ width: `${width}%` }}></div></div>}
                        {isPositive ? <div className="bg-red-500 h-1.5 rounded-r-full" style={{ width: `${width}%` }}></div> : <div className="flex-1"></div>}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-slate-500 text-sm italic">Explanation data unavailable.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default InsightsPanel;
