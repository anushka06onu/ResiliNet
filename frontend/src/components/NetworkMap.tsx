import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { getTopology } from '../services/api';

interface NetworkMapProps {
  onSelectElement: (element: any) => void;
}

const NetworkMap: React.FC<NetworkMapProps> = ({ onSelectElement }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initGraph = async () => {
      try {
        const topoData = await getTopology();
        
        if (!containerRef.current) return;

        // Transform data for cytoscape
        const elements: cytoscape.ElementDefinition[] = [];
        
        topoData.nodes.forEach((n: any) => {
          elements.push({
            data: { id: n.id, label: n.id, type: n.type }
          });
        });

        topoData.links.forEach((l: any, idx: number) => {
          elements.push({
            data: { id: `e${idx}`, source: l.source, target: l.target }
          });
        });

        const cy = cytoscape({
          container: containerRef.current,
          elements: elements,
          style: [
            {
              selector: 'node',
              style: {
                'background-color': '#3b82f6', // blue-500
                'label': 'data(label)',
                'color': '#fff',
                'font-size': '12px',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-margin-y': 5,
                'width': 24,
                'height': 24,
                'border-width': 2,
                'border-color': '#60a5fa'
              }
            },
            {
              selector: 'node[type="switch"]',
              style: {
                'shape': 'rectangle',
                'background-color': '#8b5cf6', // violet-500
                'border-color': '#a78bfa',
                'width': 30,
                'height': 30
              }
            },
            {
              selector: 'edge',
              style: {
                'width': 2,
                'line-color': '#475569', // slate-600
                'curve-style': 'bezier',
                'target-arrow-shape': 'none'
              }
            },
            {
              selector: 'edge.congested',
              style: {
                'line-color': '#ef4444', // red-500
                'width': 4,
              }
            },
            {
              selector: 'node:selected',
              style: {
                'border-width': 4,
                'border-color': '#10b981' // emerald-500
              }
            }
          ],
          layout: {
            name: 'cose',
            padding: 50,
            animate: false
          }
        });

        cy.on('tap', 'node, edge', function (evt) {
          onSelectElement({
            id: evt.target.id(),
            type: evt.target.isNode() ? 'node' : 'edge',
            data: evt.target.data()
          });
        });

        cy.on('tap', function (evt) {
          if (evt.target === cy) {
            onSelectElement(null);
          }
        });

        cyRef.current = cy;
        setLoading(false);
      } catch (e) {
        console.error("Failed to load topology", e);
        setLoading(false);
      }
    };

    initGraph();

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
      }
    };
  }, []);

  return (
    <div className="w-full h-full relative">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm z-10">
          <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
      )}
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
};

export default NetworkMap;
